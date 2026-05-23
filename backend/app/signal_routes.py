from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import InvalidOperation
from pathlib import Path
from uuid import uuid4

import pandas as pd
import requests
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from bybit_weak_intraday.execution.bybit_demo import BybitDemoAPIError
from bybit_weak_intraday.notifications.telegram import TelegramConfig, send_telegram_message, telegram_status
from bybit_weak_intraday.signals.candidates import build_scanner_watchlist, select_latest_scanner_job
from bybit_weak_intraday.signals.decision import DecisionConfig, evaluate_signal_candidate
from bybit_weak_intraday.signals.journal import append_decision_event, read_decision_journal, read_decision_journal_tail

from .execution_routes import (
    DEMO_BASE_URL,
    ExecutionConfig,
    TestShortRequest,
    count_daily_test_orders,
    demo_client_from_config,
    demo_short_event_from_request,
    execution_config_from_settings,
    journal_path_from_settings,
    submit_demo_short_order,
    _open_positions_count,
    _require_execution_api_token,
)
from .job_store import job_dir, list_jobs
from .settings import settings

router = APIRouter(prefix="/signals", tags=["signals"])


class EvaluateLatestRequest(BaseModel):
    max_candidates: int = Field(default=20, ge=1, le=200)
    notify: bool = True


class DemoAutoEntryRequest(EvaluateLatestRequest):
    dry_run: bool = False


def decision_journal_path_from_settings() -> Path:
    return Path(settings.signal_decision_journal_path)


def telegram_config_from_settings() -> TelegramConfig:
    return TelegramConfig(
        enabled=bool(settings.telegram_enabled),
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )


def current_open_positions_count(config: ExecutionConfig) -> int:
    if str(config.execution_mode).strip().lower() != "demo":
        return 0
    if config.base_url != DEMO_BASE_URL:
        return 0
    if not config.api_key.strip() or not config.api_secret.strip():
        return 0
    return _open_positions_count(demo_client_from_config(config).positions())


def load_latest_candidates(max_candidates: int = 20) -> tuple[dict | None, pd.DataFrame]:
    job = select_latest_scanner_job(list_jobs())
    if not job:
        return None, pd.DataFrame()
    try:
        out_dir = job_dir(str(job.get("job_id", "")))
        job_type = str(job.get("job_type") or "scan")
        if job_type == "causal_scan":
            signals = pd.read_csv(out_dir / "signals.csv")
            evaluations = pd.read_csv(out_dir / "evaluations.csv")
            candidates = build_scanner_watchlist(
                job_type,
                signals=signals,
                evaluations=evaluations,
                max_rows=max_candidates,
            )
        else:
            trades = pd.read_csv(out_dir / "trades.csv")
            candidates = build_scanner_watchlist(job_type, trades=trades, max_rows=max_candidates)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return job, pd.DataFrame()
    return job, candidates


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _candidate_symbol(candidate: dict) -> str:
    value = candidate.get("symbol", "")
    if _is_missing(value):
        return ""
    return str(value).strip().upper()


def _cooldown_active(symbol: str) -> bool:
    normalized_symbol = str(symbol).strip().upper()
    if not normalized_symbol:
        return False
    try:
        cooldown_minutes = int(settings.signal_cooldown_minutes)
    except (TypeError, ValueError):
        return False
    if cooldown_minutes <= 0:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    journal = read_decision_journal(decision_journal_path_from_settings())
    if journal.empty:
        return False
    for row in journal.to_dict(orient="records"):
        row_symbol = str(row.get("symbol", "")).strip().upper()
        row_status = str(row.get("status", "")).strip().lower()
        if row_symbol != normalized_symbol or row_status != "entered":
            continue
        try:
            created_at = datetime.fromisoformat(str(row.get("created_at_utc", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at.astimezone(timezone.utc) >= cutoff:
            return True
    return False


def _decision_config(
    config: ExecutionConfig,
    symbol: str,
    open_positions_count: int | None = None,
    daily_order_count: int | None = None,
) -> DecisionConfig:
    resolved_open_positions_count = (
        current_open_positions_count(config) if open_positions_count is None else int(open_positions_count)
    )
    resolved_daily_order_count = (
        count_daily_test_orders(journal_path_from_settings(), datetime.now(timezone.utc).date())
        if daily_order_count is None
        else int(daily_order_count)
    )
    return DecisionConfig(
        min_score=float(settings.signal_min_score),
        symbol_whitelist=set(config.symbol_whitelist),
        execution_mode=config.execution_mode,
        execution_enabled=config.execution_enabled,
        demo_keys_configured=bool(config.api_key.strip() and config.api_secret.strip()),
        auto_entry_enabled=bool(settings.signal_auto_entry_enabled),
        notional_usdt=float(settings.signal_default_notional_usdt),
        max_notional_usdt=float(config.max_demo_notional_usdt),
        open_positions_count=resolved_open_positions_count,
        max_open_positions=int(config.max_open_positions),
        daily_order_count=resolved_daily_order_count,
        max_daily_orders=int(config.max_daily_test_orders),
        cooldown_active=_cooldown_active(symbol),
        take_profit_pct=float(settings.signal_take_profit_pct),
        stop_loss_pct=float(settings.signal_stop_loss_pct),
    )


def _clean_value(value):
    if _is_missing(value):
        return ""
    return value


def _public_decision(row: dict) -> dict:
    keys = [
        "decision_id",
        "symbol",
        "status",
        "reason",
        "order_link_id",
        "execution_status",
        "telegram_status",
        "telegram_error",
    ]
    return {key: _clean_value(row.get(key, "")) for key in keys}


def _notification_text(row: dict) -> str:
    symbol = row.get("symbol") or "UNKNOWN"
    status = row.get("status") or ""
    reason = row.get("reason") or ""
    return f"Bybit Weak Intraday Lab signal {symbol}: {status} ({reason})"


def _append_and_notify(row: dict, notify: bool = True) -> dict:
    decision = dict(row)
    if notify:
        try:
            result = send_telegram_message(telegram_config_from_settings(), _notification_text(decision))
            decision["telegram_status"] = result.status
            decision["telegram_error"] = result.error
        except Exception:
            decision["telegram_status"] = "error"
            decision["telegram_error"] = "telegram_request_failed"
    else:
        decision["telegram_status"] = "disabled"
        decision["telegram_error"] = ""
    append_decision_event(decision_journal_path_from_settings(), decision)
    return decision


def _no_candidates_decision(job: dict | None) -> dict:
    return {
        "created_at_utc": _utc_now_iso(),
        "decision_id": uuid4().hex,
        "job_id": "" if not job else job.get("job_id", ""),
        "job_type": "" if not job else job.get("job_type", ""),
        "status": "skipped",
        "reason": "no_scanner_candidates",
    }


def _reason_from_http_exception(exc: HTTPException) -> str:
    if isinstance(exc.detail, dict):
        reason = exc.detail.get("reason")
        if reason:
            return str(reason)
    return "order_rejected"


def _preflight_counts_or_error(
    config: ExecutionConfig,
    *,
    use_open_positions: bool = True,
) -> tuple[int, int, str | None]:
    try:
        open_positions_count = current_open_positions_count(config) if use_open_positions else 0
        daily_order_count = count_daily_test_orders(journal_path_from_settings(), datetime.now(timezone.utc).date())
    except BybitDemoAPIError:
        return 0, 0, "bybit_api_error"
    except requests.RequestException:
        return 0, 0, "bybit_transport_error"
    except (InvalidOperation, ValueError, TypeError):
        return 0, 0, "bybit_api_error"
    return open_positions_count, daily_order_count, None


def _candidate_rows(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    return frame.to_dict(orient="records")


@router.get("/telegram/status")
def get_telegram_status() -> dict:
    return telegram_status(telegram_config_from_settings())


@router.post("/telegram/test")
def send_test_telegram(
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    try:
        result = send_telegram_message(telegram_config_from_settings(), "Bybit Weak Intraday Lab test message")
        return {"status": result.status, "error": result.error}
    except Exception:
        return {"status": "error", "error": "telegram_request_failed"}


@router.get("/decisions")
def decisions(limit: int = Query(default=100)) -> dict:
    clamped_limit = max(1, min(int(limit), 500))
    journal = read_decision_journal_tail(decision_journal_path_from_settings(), clamped_limit)
    rows = [] if journal.empty else [_public_decision(row) for row in journal.to_dict(orient="records")]
    return {"rows": rows, "limit": clamped_limit, "count": len(rows)}


@router.post("/evaluate-latest")
def evaluate_latest(
    req: EvaluateLatestRequest = EvaluateLatestRequest(),
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    job, candidates = load_latest_candidates(req.max_candidates)
    if candidates.empty:
        decision = _append_and_notify(_no_candidates_decision(job), notify=req.notify)
        return {"status": "evaluated", "count": 1, "decisions": [_public_decision(decision)]}

    config = execution_config_from_settings()
    open_positions_count, daily_order_count, preflight_error = _preflight_counts_or_error(config)
    decisions_out = []
    for candidate in _candidate_rows(candidates):
        symbol = _candidate_symbol(candidate)
        decision = evaluate_signal_candidate(
            candidate,
            _decision_config(
                config,
                symbol,
                open_positions_count=open_positions_count,
                daily_order_count=daily_order_count,
            ),
            job_id=str(job.get("job_id", "")) if job else "",
            job_type=str(job.get("job_type", "")) if job else "",
            require_auto_entry=False,
        )
        if preflight_error:
            decision["status"] = "error"
            decision["reason"] = preflight_error
            decision["execution_status"] = "error"
        decision = _append_and_notify(decision, notify=req.notify)
        decisions_out.append(_public_decision(decision))
    return {"status": "evaluated", "count": len(decisions_out), "decisions": decisions_out}


@router.post("/demo-auto-entry")
def demo_auto_entry(
    req: DemoAutoEntryRequest = DemoAutoEntryRequest(),
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    if not req.dry_run and not settings.signal_auto_entry_enabled:
        raise HTTPException(status_code=400, detail={"reason": "auto_entry_disabled"})

    job, candidates = load_latest_candidates(req.max_candidates)
    if candidates.empty:
        decision = _append_and_notify(_no_candidates_decision(job), notify=req.notify)
        return {"status": "evaluated", "count": 1, "decisions": [_public_decision(decision)]}

    config = execution_config_from_settings()
    open_positions_count, daily_order_count, preflight_error = _preflight_counts_or_error(
        config,
        use_open_positions=not req.dry_run,
    )
    attempted_entry = False
    entered = False
    decisions_out = []
    for candidate in _candidate_rows(candidates):
        symbol = _candidate_symbol(candidate)
        decision = evaluate_signal_candidate(
            candidate,
            _decision_config(
                config,
                symbol,
                open_positions_count=open_positions_count,
                daily_order_count=daily_order_count,
            ),
            job_id=str(job.get("job_id", "")) if job else "",
            job_type=str(job.get("job_type", "")) if job else "",
            require_auto_entry=not req.dry_run,
        )
        if preflight_error:
            decision["status"] = "error"
            decision["reason"] = preflight_error
            decision["execution_status"] = "error"
        elif decision.get("status") == "qualified":
            if attempted_entry:
                decision["status"] = "skipped"
                decision["reason"] = "already_entered_this_run"
            elif req.dry_run:
                attempted_entry = True
                decision["status"] = "skipped"
                decision["reason"] = "dry_run"
            else:
                attempted_entry = True
                order_req = TestShortRequest(
                    symbol=decision["symbol"],
                    notional_usdt=float(settings.signal_default_notional_usdt),
                    take_profit_pct=float(settings.signal_take_profit_pct),
                    stop_loss_pct=float(settings.signal_stop_loss_pct),
                )
                event = demo_short_event_from_request(order_req, config=config, event_id=str(decision["decision_id"]))
                try:
                    result = submit_demo_short_order(order_req, config=config, event=event)
                    decision["status"] = "entered"
                    decision["reason"] = "order_sent"
                    decision["order_link_id"] = result.get("order_link_id") or event.get("order_link_id", "")
                    decision["execution_status"] = result.get("status", "sent")
                    entered = True
                except HTTPException as exc:
                    decision["status"] = "error" if exc.status_code >= 500 else "rejected"
                    decision["reason"] = _reason_from_http_exception(exc)
                    decision["order_link_id"] = event.get("order_link_id", "")
                    decision["execution_status"] = "error"
                except (BybitDemoAPIError, requests.RequestException):
                    decision["status"] = "error"
                    decision["reason"] = "order_rejected"
                    decision["order_link_id"] = event.get("order_link_id", "")
                    decision["execution_status"] = "error"
        decision = _append_and_notify(decision, notify=req.notify)
        decisions_out.append(_public_decision(decision))

    status = "entered" if entered else "evaluated"
    return {"status": status, "count": len(decisions_out), "decisions": decisions_out}
