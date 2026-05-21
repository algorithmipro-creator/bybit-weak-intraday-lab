from __future__ import annotations

import os
import time
from io import StringIO
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from ui.account_backtest import AccountBacktestSettings, run_account_backtest
from ui.bot_monitor import (
    build_scanner_watchlist,
    normalize_open_orders,
    normalize_positions,
    select_latest_scanner_job,
    summarize_wallet,
)
from ui.result_summary import best_grid_result, trade_result_summary
from ui.table_totals import append_account_total_row, append_trade_total_row

DEFAULT_API = os.getenv("BWI_API_URL", "http://backend:8000")
ACTIVE_STATUSES = {"queued", "running"}

st.set_page_config(page_title="Bybit Weak Intraday Lab", layout="wide")
st.title("Bybit Weak Intraday Lab")
st.caption("Research dashboard for weak-continuation and pump-and-fade Bybit USDT-perp scans. No live orders.")


def api_get(path: str, api_url: str, token: str | None = None):
    headers = {"X-BWI-Execution-Token": token} if token else None
    r = requests.get(f"{api_url}{path}", timeout=30, headers=headers)
    r.raise_for_status()
    return r


def api_post(path: str, payload: dict, api_url: str, token: str | None = None):
    headers = {"X-BWI-Execution-Token": token} if token else None
    r = requests.post(f"{api_url}{path}", json=payload, timeout=30, headers=headers)
    r.raise_for_status()
    return r


def _safe_error(exc, token: str | None = None) -> str:
    message = str(exc)
    if token:
        message = message.replace(token, "[redacted]")
    return message


def api_json_or_error(path: str, api_url: str, token: str | None = None):
    try:
        response = api_get(path, api_url, token=token)
        return response.json(), None
    except Exception as exc:
        return None, _safe_error(exc, token)


def _result_list(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    return ((payload.get("result") or {}).get("list") or []) or []


def parse_float_grid(value: str) -> list[float]:
    return [float(x.strip()) for x in value.replace("\n", ",").split(",") if x.strip()]


def csv_to_frame(csv_text: str) -> pd.DataFrame:
    return pd.read_csv(StringIO(csv_text)) if csv_text.strip() else pd.DataFrame()


def pct(value: Any, multiplier: float = 1.0) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * multiplier:.2f}%"


def number(value: Any, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{decimals}f}"


def money(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"${float(value):,.2f}"


def signed_money(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    parsed = float(value)
    sign = "+" if parsed > 0 else ""
    return f"{sign}${parsed:,.2f}"


def compact_count(value: Any) -> str:
    if value is None or pd.isna(value):
        return "0"
    return str(int(value))


def render_job_status(meta: dict) -> None:
    status = str(meta.get("status") or "unknown")
    message = meta.get("message") or ""
    if status == "error":
        st.error(message or "Job failed before writing result files.")
    elif status in ACTIVE_STATUSES:
        st.info(message or "Job is still running.")
    elif status == "done":
        st.success(message or "Job complete.")
    else:
        st.warning(message or f"Job status: {status}")


def render_scan_overview(trades: pd.DataFrame) -> None:
    summary = trade_result_summary(trades)
    st.subheader("Result overview")
    cols = st.columns(7)
    cols[0].metric("Trades", int(summary["trades"]))
    cols[1].metric("TP rate", pct(summary["tp_rate_pct"]))
    cols[2].metric("SL rate", pct(summary["sl_rate_pct"]))
    cols[3].metric("Avg PnL", pct(summary["avg_pnl_pct"]))
    cols[4].metric("Median PnL", pct(summary["median_pnl_pct"]))
    cols[5].metric("Avg MFE", pct(summary["avg_mfe_pct"]))
    cols[6].metric("Avg MAE", pct(summary["avg_mae_pct"]))
    if summary["trades"] == 0:
        st.warning("No candidate trades matched this job's filters.")


def render_account_backtest(trades: pd.DataFrame) -> None:
    st.subheader("Account Backtest")
    with st.expander("Account assumptions", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        initial_equity = c1.number_input(
            "Initial equity USD",
            min_value=100.0,
            value=10_000.0,
            step=500.0,
            format="%.2f",
        )
        position_size = c2.number_input(
            "Position size %",
            min_value=0.1,
            max_value=100.0,
            value=10.0,
            step=1.0,
            format="%.2f",
        )
        leverage = c3.number_input("Leverage", min_value=0.1, value=1.0, step=0.5, format="%.2f")
        entry_fee = c4.number_input("Entry fee %", min_value=0.0, value=0.06, step=0.01, format="%.3f")
        c5, c6, c7 = st.columns(3)
        exit_fee = c5.number_input("Exit fee %", min_value=0.0, value=0.06, step=0.01, format="%.3f")
        slippage = c6.number_input("Slippage %", min_value=0.0, value=0.0, step=0.01, format="%.3f")
        funding = c7.number_input("Funding %", min_value=0.0, value=0.0, step=0.01, format="%.3f")
        st.caption("Sequential close-time research model. It does not reserve margin for overlapping positions.")

    settings = AccountBacktestSettings(
        initial_equity_usd=float(initial_equity),
        position_size_pct=float(position_size),
        leverage=float(leverage),
        entry_fee_pct=float(entry_fee),
        exit_fee_pct=float(exit_fee),
        slippage_pct=float(slippage),
        funding_pct=float(funding),
    )
    try:
        summary, curve = run_account_backtest(trades, settings)
    except ValueError as exc:
        st.error(str(exc))
        return

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Final equity", money(summary["final_equity_usd"]))
    c2.metric("Total return", pct(summary["total_return_pct"]))
    c3.metric("Net PnL", money(summary["net_pnl_usd"]))
    c4.metric("Max DD", pct(summary["max_drawdown_pct"]))
    c5.metric("Win rate", pct(summary["win_rate_pct"]))
    c6.metric("Skipped", int(summary["skipped_trades"]))

    if curve.empty:
        st.info("No account backtest rows available for these trades.")
        return

    chart_left, chart_right = st.columns(2)
    curve_for_chart = curve.copy()
    curve_for_chart["trade_label"] = curve_for_chart.apply(
        lambda row: f"{row.get('date') or ''} {row.get('symbol') or ''}".strip(),
        axis=1,
    )
    with chart_left:
        st.plotly_chart(
            px.line(
                curve_for_chart,
                x="exit_time_utc",
                y="equity_after_usd",
                markers=True,
                hover_data=["symbol", "outcome", "net_pnl_usd", "drawdown_pct"],
                title="Equity curve",
            ),
            use_container_width=True,
        )
    with chart_right:
        st.plotly_chart(
            px.bar(
                curve_for_chart,
                x="trade_label",
                y="net_pnl_usd",
                color="outcome" if "outcome" in curve_for_chart.columns else None,
                hover_data=["pnl_underlying_pct", "account_return_pct", "costs_usd"],
                title="Per-trade account PnL",
            ),
            use_container_width=True,
        )

    with st.expander("Account trade details", expanded=False):
        st.dataframe(
            append_account_total_row(curve, initial_equity_usd=float(summary["initial_equity_usd"])),
            use_container_width=True,
            hide_index=True,
        )


def render_causal_overview(signals: pd.DataFrame) -> None:
    st.subheader("Causal Signal Overview")
    count = int(len(signals))
    modes = signals["mode"].astype(str) if "mode" in signals.columns else pd.Series(dtype=str)
    avg_score = signals["score"].mean() if "score" in signals.columns and not signals.empty else 0.0
    cols = st.columns(4)
    cols[0].metric("Signals", count)
    cols[1].metric("Weak", int((modes == "weak").sum()))
    cols[2].metric("Pump", int((modes == "pump").sum()))
    cols[3].metric("Avg score", number(avg_score))
    if signals.empty:
        st.warning("No causal signals matched this job's filters.")


def render_causal_evaluation_overview(evaluations: pd.DataFrame) -> None:
    st.subheader("Post-Signal Evaluation")
    summary = trade_result_summary(evaluations)
    cols = st.columns(7)
    cols[0].metric("Evaluated", int(summary["trades"]))
    cols[1].metric("TP rate", pct(summary["tp_rate_pct"]))
    cols[2].metric("SL rate", pct(summary["sl_rate_pct"]))
    cols[3].metric("Avg PnL", pct(summary["avg_pnl_pct"]))
    cols[4].metric("Median PnL", pct(summary["median_pnl_pct"]))
    cols[5].metric("Avg MFE", pct(summary["avg_mfe_pct"]))
    cols[6].metric("Avg MAE", pct(summary["avg_mae_pct"]))
    if evaluations.empty:
        st.info("No post-signal evaluation rows for this causal job.")


def render_grid_overview(grid: pd.DataFrame) -> None:
    st.subheader("Best grid result")
    best = best_grid_result(grid)
    if best is None:
        st.warning("No TP/SL grid combination produced candidate trades.")
        return
    cols = st.columns(6)
    cols[0].metric("Best TP", pct(best.get("tp_pct")))
    cols[1].metric("Best SL", pct(best.get("sl_pct")))
    cols[2].metric("Trades", int(best.get("trades") or 0))
    cols[3].metric("Avg PnL", pct(best.get("avg_underlying_pnl")))
    cols[4].metric("TP rate", pct(best.get("tp_rate"), multiplier=100))
    cols[5].metric("Avg exit min", number(best.get("avg_minutes_to_exit"), decimals=0))


def _render_result_table(title: str, payload: dict | None, error: str | None) -> None:
    st.markdown(f"**{title}**")
    if error:
        st.info(f"{title} unavailable: {error}")
        return
    rows = _result_list(payload)
    if not rows:
        st.info(f"No {title.lower()} rows returned.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _symbol_query(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    return f"?symbol={cleaned}" if cleaned else ""


def _safe_jobs(api_url: str) -> list[dict]:
    try:
        jobs = api_get("/jobs", api_url).json()
    except Exception:
        return []
    return jobs if isinstance(jobs, list) else []


def _frame_from_rows(rows) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _load_scanner_watchlist(api_url: str, jobs: list[dict]) -> pd.DataFrame:
    latest_job = select_latest_scanner_job(jobs)
    if not latest_job:
        return pd.DataFrame()

    job_id = latest_job.get("job_id")
    if not job_id:
        return pd.DataFrame()

    job_type = latest_job.get("job_type") or "scan"
    try:
        if job_type == "causal_scan":
            signals = csv_to_frame(api_get(f"/jobs/{job_id}/signals.csv", api_url).text)
            evaluations = csv_to_frame(api_get(f"/jobs/{job_id}/evaluations.csv", api_url).text)
            return build_scanner_watchlist(job_type, signals=signals, evaluations=evaluations)

        trades = csv_to_frame(api_get(f"/jobs/{job_id}/trades.csv", api_url).text)
        return build_scanner_watchlist(job_type, trades=trades)
    except Exception:
        return pd.DataFrame()


def render_demo_test_short_form(api_url: str, execution_token: str, status_payload: dict) -> None:
    execution_token = execution_token.strip()
    whitelist = status_payload.get("whitelist") or []
    default_symbol = str(whitelist[0]) if whitelist else "ENAUSDT"

    with st.form("bot_monitor_demo_test_short_form"):
        form_cols = st.columns(4)
        symbol = form_cols[0].text_input("Symbol", default_symbol).strip().upper()
        notional = form_cols[1].number_input("Notional USDT", min_value=1.0, value=5.0, step=1.0, format="%.2f")
        take_profit = form_cols[2].number_input("Take profit %", min_value=0.1, value=6.0, step=0.5, format="%.2f")
        stop_loss = form_cols[3].number_input("Stop loss %", min_value=0.1, value=7.0, step=0.5, format="%.2f")
        submit = st.form_submit_button("Place Demo Test Short")

    if submit:
        if not execution_token:
            st.error("Enter the execution API token in the sidebar before placing a demo test short.")
            return

        payload = {
            "symbol": symbol,
            "notional_usdt": float(notional),
            "take_profit_pct": float(take_profit) / 100.0,
            "stop_loss_pct": float(stop_loss) / 100.0,
        }
        try:
            response = api_post("/execution/demo/place-test-short", payload, api_url, token=execution_token)
            st.success("Demo test short submitted.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Demo test short rejected or failed: {_safe_error(exc, execution_token)}")


def render_bot_monitor(api_url: str, execution_token: str) -> None:
    execution_token = execution_token.strip()
    st.header("Bot Monitor")

    health_payload, health_error = api_json_or_error("/health", api_url)
    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)
    status_payload = status_payload or {}
    limits = status_payload.get("limits") or {}
    jobs = _safe_jobs(api_url)
    scanner_watchlist = _load_scanner_watchlist(api_url, jobs)

    if status_error:
        st.warning(f"Execution status unavailable: {status_error}")

    status_cols = st.columns(6)
    status_cols[0].metric("Backend", "offline" if health_error else "online")
    status_cols[1].metric("Mode", status_payload.get("mode") or "unknown")
    status_cols[2].metric("Execution", "enabled" if status_payload.get("enabled") else "disabled")
    status_cols[3].metric("API keys", "configured" if status_payload.get("configured") else "missing")
    token_status = "entered" if execution_token else ("configured" if status_payload.get("api_token_configured") else "missing")
    status_cols[4].metric("Token", token_status)
    status_cols[5].metric("Max notional", money(limits.get("max_demo_notional_usdt")))
    st.caption("Bybit Demo monitor, reads account/scanner state and does not auto-enter signals.")

    if health_error:
        st.warning(f"Backend health unavailable: {health_error}")

    wallet_payload = positions_payload = orders_payload = journal_payload = None
    wallet_error = positions_error = orders_error = journal_error = None
    positions_rows: list[dict] = []
    orders_rows: list[dict] = []
    wallet_summary = summarize_wallet(None)

    if not execution_token:
        st.info("Enter the execution API token in the sidebar to load demo account data and order controls.")
    else:
        wallet_payload, wallet_error = api_json_or_error("/execution/demo/wallet", api_url, token=execution_token)
        positions_payload, positions_error = api_json_or_error("/execution/demo/positions", api_url, token=execution_token)
        orders_payload, orders_error = api_json_or_error("/execution/demo/open-orders", api_url, token=execution_token)
        journal_payload, journal_error = api_json_or_error("/execution/demo/journal?limit=25", api_url, token=execution_token)

        if wallet_error:
            st.warning(f"Wallet unavailable: {wallet_error}")
        else:
            wallet_summary = summarize_wallet(wallet_payload)

        if orders_error:
            st.warning(f"Open orders unavailable: {orders_error}")
        else:
            orders_rows = normalize_open_orders(orders_payload)

        if positions_error:
            st.warning(f"Positions unavailable: {positions_error}")
        else:
            positions_rows = normalize_positions(positions_payload, orders_payload if not orders_error else None)

        if journal_error:
            st.warning(f"Execution history unavailable: {journal_error}")

    account_cols = st.columns(8)
    account_cols[0].metric("Equity", money(wallet_summary.get("equity")))
    account_cols[1].metric("Wallet", money(wallet_summary.get("wallet_balance")))
    account_cols[2].metric("Available", money(wallet_summary.get("available_balance")))
    account_cols[3].metric("Margin used", money(wallet_summary.get("margin_used")))
    account_cols[4].metric("Unrealized PnL", signed_money(wallet_summary.get("unrealized_pnl")))
    account_cols[5].metric("Positions", compact_count(len(positions_rows)))
    account_cols[6].metric("Open orders", compact_count(len(orders_rows)))
    account_cols[7].metric("Scanner signals", compact_count(len(scanner_watchlist)))

    positions_frame = _frame_from_rows(positions_rows)
    orders_frame = _frame_from_rows(orders_rows)
    journal_rows = _result_list(journal_payload)
    journal_frame = _frame_from_rows(journal_rows)

    main_left, main_right = st.columns(2)
    with main_left:
        st.subheader("Open Positions")
        if positions_error:
            st.info("Positions are unavailable.")
        elif positions_frame.empty:
            st.info("No open positions.")
        else:
            st.dataframe(positions_frame, use_container_width=True, hide_index=True)
    with main_right:
        st.subheader("Scanner Watchlist")
        if scanner_watchlist.empty:
            st.info("No scanner watchlist rows available.")
        else:
            st.dataframe(scanner_watchlist, use_container_width=True, hide_index=True)

    secondary_left, secondary_right = st.columns(2)
    with secondary_left:
        st.subheader("Open Orders")
        if orders_error:
            st.info("Open orders are unavailable.")
        elif orders_frame.empty:
            st.info("No open orders.")
        else:
            st.dataframe(orders_frame, use_container_width=True, hide_index=True)
    with secondary_right:
        st.subheader("Execution History")
        if journal_error:
            st.info("Execution history is unavailable.")
        elif journal_frame.empty:
            st.info("No execution history rows.")
        else:
            history_columns = [
                column
                for column in [
                    "created_at_utc",
                    "symbol",
                    "side",
                    "requested_notional_usdt",
                    "qty",
                    "take_profit",
                    "stop_loss",
                    "status",
                    "reason",
                    "bybit_ret_code",
                    "bybit_ret_msg",
                ]
                if column in journal_frame.columns
            ]
            st.dataframe(journal_frame[history_columns], use_container_width=True, hide_index=True)

    with st.expander("Controlled demo test short", expanded=False):
        render_demo_test_short_form(api_url, execution_token, status_payload)


def render_demo_execution(api_url: str, execution_token: str) -> None:
    execution_token = execution_token.strip()
    st.subheader("Bybit Demo Execution")
    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)
    if status_error:
        st.error(f"Execution status unavailable: {status_error}")
        return

    status_payload = status_payload or {}
    limits = status_payload.get("limits") or {}
    whitelist = status_payload.get("whitelist") or []

    cols = st.columns(5)
    cols[0].metric("Mode", status_payload.get("mode") or "unknown")
    cols[1].metric("Enabled", "yes" if status_payload.get("enabled") else "no")
    cols[2].metric("API keys configured", "yes" if status_payload.get("configured") else "no")
    cols[3].metric("Execution token configured", "yes" if status_payload.get("api_token_configured") else "no")
    cols[4].metric("Journal rows", int(status_payload.get("journal_rows") or 0))
    st.caption("Bybit Demo only. This panel does not place mainnet orders or auto-enter from signals.")

    meta_left, meta_right = st.columns(2)
    with meta_left:
        st.markdown("**Endpoint**")
        st.code(status_payload.get("base_url") or "n/a", language="text")
    with meta_right:
        st.markdown("**Whitelist and limits**")
        whitelist_text = ", ".join(str(symbol) for symbol in whitelist) if whitelist else "none"
        limits_text = (
            f"Whitelist: {whitelist_text}\n"
            f"Max notional: {limits.get('max_demo_notional_usdt', 'n/a')} USDT\n"
            f"Max open positions: {limits.get('max_open_positions', 'n/a')}\n"
            f"Max daily test orders: {limits.get('max_daily_test_orders', 'n/a')}"
        )
        st.code(limits_text, language="text")

    if not execution_token:
        st.info("Enter the execution API token in the sidebar to load demo account data and order controls.")
        return

    symbol_options = [""] + [str(symbol) for symbol in whitelist]
    symbol_filter = st.selectbox(
        "Symbol filter for positions and open orders",
        symbol_options,
        format_func=lambda value: "All whitelisted symbols" if value == "" else value,
    )
    query = _symbol_query(symbol_filter)

    wallet_payload, wallet_error = api_json_or_error("/execution/demo/wallet", api_url, token=execution_token)
    positions_payload, positions_error = api_json_or_error(
        f"/execution/demo/positions{query}",
        api_url,
        token=execution_token,
    )
    orders_payload, orders_error = api_json_or_error(
        f"/execution/demo/open-orders{query}",
        api_url,
        token=execution_token,
    )

    tab_wallet, tab_positions, tab_orders = st.tabs(["Wallet", "Positions", "Open Orders"])
    with tab_wallet:
        _render_result_table("Wallet", wallet_payload, wallet_error)
    with tab_positions:
        _render_result_table("Positions", positions_payload, positions_error)
    with tab_orders:
        _render_result_table("Open orders", orders_payload, orders_error)

    default_symbol = str(whitelist[0]) if whitelist else "ENAUSDT"
    with st.form("demo_test_short_form"):
        st.markdown("**Controlled demo test short**")
        form_cols = st.columns(4)
        symbol = form_cols[0].text_input("Symbol", default_symbol).strip().upper()
        notional = form_cols[1].number_input("Notional USDT", min_value=1.0, value=5.0, step=1.0, format="%.2f")
        take_profit = form_cols[2].number_input("Take profit %", min_value=0.1, value=6.0, step=0.5, format="%.2f")
        stop_loss = form_cols[3].number_input("Stop loss %", min_value=0.1, value=7.0, step=0.5, format="%.2f")
        submit = st.form_submit_button("Place Demo Test Short")

    if submit:
        payload = {
            "symbol": symbol,
            "notional_usdt": float(notional),
            "take_profit_pct": float(take_profit) / 100.0,
            "stop_loss_pct": float(stop_loss) / 100.0,
        }
        try:
            response = api_post("/execution/demo/place-test-short", payload, api_url, token=execution_token)
            st.success("Demo test short submitted.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Demo test short rejected or failed: {_safe_error(exc, execution_token)}")


with st.sidebar:
    api_url = st.text_input("Backend API URL", DEFAULT_API).rstrip("/")
    execution_token = st.text_input("Execution API token", type="password")
    auto_refresh = st.checkbox("Auto-refresh active jobs", value=True)

    st.header("Scan settings")
    job_mode = st.radio("Job type", ["Archive scan", "Causal signal scan", "TP/SL optimizer"], horizontal=True)
    start = st.text_input("Start date", "2026-03-18")
    end = st.text_input("End date", "2026-03-27")
    symbols_raw = st.text_area("Symbols", "EIGENUSDT,GRASSUSDT,RVNUSDT,ENJUSDT,JTOUSDT,STGUSDT,ENAUSDT", height=100)
    full_universe = st.checkbox("Full archive universe", value=False)
    max_symbols = st.number_input("Max symbols", min_value=0, max_value=2000, value=0, step=10)
    min_turnover = st.number_input("Min turnover USDT", min_value=0, value=1_000_000, step=250_000)
    weak_threshold = st.slider("Weak threshold", 0, 15, 9)
    pump_threshold = st.slider("Pump threshold", 0, 15, 9)
    tp_weak = st.number_input("TP weak underlying", value=0.06, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
    sl_weak = st.number_input("SL weak underlying", value=0.07, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
    tp_pump = st.number_input("TP pump underlying", value=0.08, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
    sl_pump = st.number_input("SL pump underlying", value=0.07, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
    max_hold_min = st.number_input("Max hold minutes", min_value=15, max_value=1440, value=720, step=15)
    if job_mode == "TP/SL optimizer":
        tp_grid_raw = st.text_input("TP grid", "0.04,0.06,0.08")
        sl_grid_raw = st.text_input("SL grid", "0.05,0.07")
    run = st.button("Start job", type="primary")

if run:
    symbols = [s.strip().upper() for s in symbols_raw.replace("\n", ",").split(",") if s.strip()]
    payload = {
        "start": start,
        "end": end,
        "symbols": symbols,
        "full_universe": full_universe,
        "include_majors": False,
        "max_symbols": int(max_symbols),
        "min_turnover": float(min_turnover),
        "weak_threshold": int(weak_threshold),
        "pump_threshold": int(pump_threshold),
        "tp_weak": float(tp_weak),
        "sl_weak": float(sl_weak),
        "tp_pump": float(tp_pump),
        "sl_pump": float(sl_pump),
        "max_hold_min": float(max_hold_min),
    }
    try:
        path = "/jobs/scan"
        if job_mode == "Causal signal scan":
            path = "/jobs/scan-causal"
        if job_mode == "TP/SL optimizer":
            payload["tp_grid"] = parse_float_grid(tp_grid_raw)
            payload["sl_grid"] = parse_float_grid(sl_grid_raw)
            path = "/jobs/optimize-tp-sl"
        resp = api_post(path, payload, api_url).json()
        st.session_state["selected_job_id"] = resp["job_id"]
        st.success(f"Job queued: {resp['job_id']}")
    except Exception as exc:
        st.error(f"Failed to start job: {exc}")

st.divider()
render_bot_monitor(api_url, execution_token)

st.header("Jobs")
try:
    jobs = api_get("/jobs", api_url).json()
    if jobs:
        jobs_df = pd.DataFrame(jobs)
        if "created_at" in jobs_df.columns:
            jobs_df = jobs_df.sort_values("created_at", ascending=False, na_position="last")

        display_columns = [
            col
            for col in [
                "job_id",
                "job_type",
                "status",
                "message",
                "metrics_rows",
                "trades_rows",
                "signals_rows",
                "evaluations_rows",
                "grid_rows",
                "grid_trades_rows",
                "created_at",
                "updated_at",
            ]
            if col in jobs_df.columns
        ]
        st.dataframe(jobs_df[display_columns], use_container_width=True, hide_index=True)

        job_ids = jobs_df["job_id"].tolist()
        selected_from_state = st.session_state.get("selected_job_id")
        default_index = job_ids.index(selected_from_state) if selected_from_state in job_ids else 0
        selected_job = st.selectbox("Open job", job_ids, index=default_index)
        st.session_state["selected_job_id"] = selected_job
    else:
        st.info("No jobs yet. Start a scan from the sidebar.")
        selected_job = None
except Exception as exc:
    st.warning(f"Backend is not reachable yet: {exc}")
    selected_job = None

if selected_job:
    try:
        meta = api_get(f"/jobs/{selected_job}", api_url).json()
    except Exception as exc:
        st.error(f"Failed to load selected job: {exc}")
        meta = None

    if meta:
        st.subheader(f"Selected job: {selected_job}")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Status", meta.get("status") or "unknown")
        c2.metric("Type", meta.get("job_type") or "scan")
        c3.metric("Result rows", meta.get("metrics_rows") or meta.get("grid_rows") or meta.get("signals_rows") or 0)
        c4.metric("Trade rows", meta.get("trades_rows") or meta.get("grid_trades_rows") or meta.get("evaluations_rows") or 0)
        c5.metric("Updated", (meta.get("updated_at") or "")[:19])
        render_job_status(meta)

        status = meta.get("status")
        if status in ACTIVE_STATUSES and auto_refresh:
            time.sleep(3)
            st.rerun()
        elif status == "done" and meta.get("job_type") == "causal_scan":
            signals_csv = ""
            evaluations_csv = ""
            try:
                signals_csv = api_get(f"/jobs/{selected_job}/signals.csv", api_url).text
                evaluations_csv = api_get(f"/jobs/{selected_job}/evaluations.csv", api_url).text
                signals = csv_to_frame(signals_csv)
                evaluations = csv_to_frame(evaluations_csv)
            except Exception as exc:
                st.error(f"Failed to load causal results: {exc}")
                signals = pd.DataFrame()
                evaluations = pd.DataFrame()

            render_causal_overview(signals)
            render_causal_evaluation_overview(evaluations)
            tab1, tab2, tab3 = st.tabs(["Signals", "Evaluations", "Charts"])
            with tab1:
                st.download_button("Download signals CSV", signals_csv, file_name=f"{selected_job}_signals.csv")
                st.dataframe(signals, use_container_width=True, hide_index=True)
            with tab2:
                st.download_button("Download evaluations CSV", evaluations_csv, file_name=f"{selected_job}_evaluations.csv")
                st.dataframe(append_trade_total_row(evaluations), use_container_width=True, hide_index=True)
            with tab3:
                if not signals.empty or not evaluations.empty:
                    if {"signal_time_utc", "score", "mode"}.issubset(signals.columns):
                        st.plotly_chart(
                            px.scatter(
                                signals,
                                x="signal_time_utc",
                                y="score",
                                color="mode",
                                hover_data=["symbol", "signal_price", "turnover_so_far_usdt", "turnover_ratio_so_far"],
                                title="Causal signals by time and score",
                            ),
                            use_container_width=True,
                        )
                    if "mode" in signals.columns:
                        st.plotly_chart(px.histogram(signals, x="mode", title="Causal signal modes"), use_container_width=True)
                    if not evaluations.empty and {"mfe_after_entry_pct", "mae_after_entry_pct", "mode"}.issubset(evaluations.columns):
                        st.plotly_chart(
                            px.scatter(
                                evaluations,
                                x="mae_after_entry_pct",
                                y="mfe_after_entry_pct",
                                color="mode",
                                hover_data=["symbol", "date", "outcome", "pnl_underlying_pct"],
                                title="Causal MFE vs MAE after signal",
                            ),
                            use_container_width=True,
                        )
                    if not evaluations.empty and "outcome" in evaluations.columns:
                        st.plotly_chart(px.histogram(evaluations, x="outcome", title="Causal evaluation outcomes"), use_container_width=True)
                    if not evaluations.empty and {"score", "pnl_underlying_pct", "mode"}.issubset(evaluations.columns):
                        st.plotly_chart(
                            px.scatter(
                                evaluations,
                                x="score",
                                y="pnl_underlying_pct",
                                color="mode",
                                hover_data=["symbol", "date", "outcome"],
                                title="Causal score vs post-signal PnL",
                            ),
                            use_container_width=True,
                        )
                else:
                    st.info("No causal result rows in this job.")
        elif status == "done" and meta.get("job_type") == "tp_sl_grid":
            grid_csv = ""
            grid_trades_csv = ""
            try:
                grid_csv = api_get(f"/jobs/{selected_job}/grid.csv", api_url).text
                grid_trades_csv = api_get(f"/jobs/{selected_job}/grid_trades.csv", api_url).text
                grid = csv_to_frame(grid_csv)
                grid_trades = csv_to_frame(grid_trades_csv)
            except Exception as exc:
                st.error(f"Failed to load optimizer results: {exc}")
                grid = pd.DataFrame()
                grid_trades = pd.DataFrame()

            render_grid_overview(grid)
            tab1, tab2, tab3 = st.tabs(["Grid Summary", "Grid Trades", "Charts"])
            with tab1:
                st.download_button("Download grid CSV", grid_csv, file_name=f"{selected_job}_grid.csv")
                st.dataframe(grid, use_container_width=True, hide_index=True)
            with tab2:
                st.download_button("Download grid trades CSV", grid_trades_csv, file_name=f"{selected_job}_grid_trades.csv")
                st.dataframe(append_trade_total_row(grid_trades), use_container_width=True, hide_index=True)
            with tab3:
                if not grid.empty and {"tp_pct", "sl_pct", "avg_underlying_pnl"}.issubset(grid.columns):
                    st.plotly_chart(
                        px.scatter(
                            grid,
                            x="tp_pct",
                            y="sl_pct",
                            size="trades",
                            color="avg_underlying_pnl",
                            hover_data=["tp_rate", "sl_rate", "avg_minutes_to_exit"],
                            title="TP/SL grid average PnL",
                        ),
                        use_container_width=True,
                    )
                if not grid_trades.empty and {"outcome", "tp_pct", "sl_pct"}.issubset(grid_trades.columns):
                    st.plotly_chart(
                        px.histogram(grid_trades, x="outcome", color="tp_pct", title="Grid outcomes"),
                        use_container_width=True,
                    )
                if grid.empty and grid_trades.empty:
                    st.info("No optimizer result files contain rows.")
        elif status == "done":
            trades_csv = ""
            metrics_csv = ""
            try:
                trades_csv = api_get(f"/jobs/{selected_job}/trades.csv", api_url).text
                metrics_csv = api_get(f"/jobs/{selected_job}/metrics.csv", api_url).text
                trades = csv_to_frame(trades_csv)
                metrics = csv_to_frame(metrics_csv)
            except Exception as exc:
                st.error(f"Failed to load scan results: {exc}")
                trades = pd.DataFrame()
                metrics = pd.DataFrame()

            render_scan_overview(trades)
            render_account_backtest(trades)
            tab1, tab2, tab3 = st.tabs(["Trades", "Metrics", "Charts"])
            with tab1:
                st.download_button("Download trades CSV", trades_csv, file_name=f"{selected_job}_trades.csv")
                st.dataframe(append_trade_total_row(trades), use_container_width=True, hide_index=True)
            with tab2:
                st.download_button("Download metrics CSV", metrics_csv, file_name=f"{selected_job}_metrics.csv")
                st.dataframe(metrics, use_container_width=True, hide_index=True)
            with tab3:
                if not trades.empty:
                    left, right = st.columns(2)
                    with left:
                        st.plotly_chart(px.histogram(trades, x="outcome", title="Outcomes"), use_container_width=True)
                    with right:
                        if {"mfe_after_entry_pct", "mae_after_entry_pct", "mode"}.issubset(trades.columns):
                            st.plotly_chart(
                                px.scatter(
                                    trades,
                                    x="mae_after_entry_pct",
                                    y="mfe_after_entry_pct",
                                    color="mode",
                                    hover_data=["symbol", "date", "outcome"],
                                    title="MFE vs MAE after entry",
                                ),
                                use_container_width=True,
                            )
                    if {"candidate_score", "turnover_usdt", "symbol"}.issubset(trades.columns):
                        st.plotly_chart(
                            px.scatter(
                                trades,
                                x="candidate_score",
                                y="turnover_usdt",
                                size="mfe_after_entry_pct" if "mfe_after_entry_pct" in trades.columns else None,
                                hover_data=["symbol", "date", "mode", "outcome"],
                                title="Score vs turnover",
                            ),
                            use_container_width=True,
                        )
                else:
                    st.info("No candidate trades in this job.")
