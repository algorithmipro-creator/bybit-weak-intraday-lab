from __future__ import annotations

import os
import time
from io import StringIO
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from ui.account_backtest import AccountBacktestSettings, run_account_backtest
from ui.app_navigation import (
    API_URL_KEY,
    EXECUTION_TOKEN_KEY,
    NAV_PAGES,
    SELECTED_PAGE_KEY,
    connection_values,
    disconnect,
    ensure_navigation_state,
    is_connected,
    mark_connected,
    normalize_page,
)
from ui.bot_monitor import (
    build_scanner_watchlist,
    normalize_open_orders,
    normalize_positions,
    select_latest_scanner_job,
    summarize_wallet,
)
from ui.bot_monitor_visual import (
    VisualMetric,
    VisualPill,
    build_executive_overview_html,
    build_signal_decisions_panel_html,
    build_visual_panels_html,
    monitor_visual_css,
)
from ui.result_summary import best_grid_result, trade_result_summary
from ui.table_totals import append_account_total_row, append_trade_total_row

DEFAULT_API = os.getenv("BWI_API_URL", "http://backend:8000")
ACTIVE_STATUSES = {"queued", "running"}


def render_app_shell_chrome() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                max-width: 1360px;
                padding-top: 1.1rem;
                padding-left: 1.35rem;
                padding-right: 1.35rem;
            }
            .bwi-app-header {
                margin: -0.15rem 0 0.7rem 0;
                padding: 0;
            }
            .bwi-app-title {
                margin: 0;
                font-size: 1.05rem;
                line-height: 1.2;
                font-weight: 650;
                letter-spacing: 0;
                color: var(--text-color);
            }
            .bwi-app-subtitle {
                margin: 0.16rem 0 0 0;
                font-size: 0.76rem;
                line-height: 1.25;
                letter-spacing: 0;
                color: var(--text-color);
                opacity: 0.68;
            }
        </style>
        <div class="bwi-app-header">
            <div class="bwi-app-title">Bybit Weak Intraday Lab</div>
            <div class="bwi-app-subtitle">
                Research dashboard for weak-continuation and pump-and-fade Bybit USDT-perp scans. No live orders.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Bybit Weak Intraday Lab", layout="wide")
render_app_shell_chrome()


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


def _journal_rows(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


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


def _status_tone(value: bool | None) -> str:
    return "success" if value else "warning"


def _monitor_status_label(health_error: str | None, status_payload: dict) -> str:
    if health_error:
        return "BACKEND OFFLINE"
    if status_payload.get("mode") == "demo" and status_payload.get("configured"):
        return "DEMO CONNECTED"
    if status_payload.get("mode") == "demo":
        return "DEMO CONFIG NEEDED"
    return "MONITOR CHECK"


def _render_variant_a_visual_overview(
    *,
    health_error: str | None,
    status_payload: dict,
    limits: dict,
    execution_token: str,
    wallet_summary: dict,
    positions_rows: list[dict],
    orders_rows: list[dict],
    scanner_watchlist: pd.DataFrame,
) -> None:
    scanner_count = len(scanner_watchlist)
    metrics = [
        VisualMetric(
            "Equity",
            money(wallet_summary.get("equity")),
            detail=f"Wallet {money(wallet_summary.get('wallet_balance'))} | Available {money(wallet_summary.get('available_balance'))}",
        ),
        VisualMetric(
            "Unreal PnL",
            signed_money(wallet_summary.get("unrealized_pnl")),
            _pnl_tone(wallet_summary.get("unrealized_pnl")),
        ),
        VisualMetric(
            "Margin",
            money(wallet_summary.get("margin_used")),
            detail=f"Positions {len(positions_rows)} | Orders {len(orders_rows)}",
        ),
        VisualMetric("Signals", f"{scanner_count} waiting" if scanner_count else "0 waiting", "accent"),
    ]
    pills = [
        VisualPill("Backend", "online" if not health_error else "offline", _status_tone(not health_error)),
        VisualPill("Mode", str(status_payload.get("mode") or "unknown"), _status_tone(status_payload.get("mode") == "demo")),
        VisualPill("Execution", "enabled" if status_payload.get("enabled") else "disabled", _status_tone(status_payload.get("enabled"))),
        VisualPill("Keys", "configured" if status_payload.get("configured") else "missing", _status_tone(status_payload.get("configured"))),
        VisualPill("Token", "entered" if execution_token else "locked", _status_tone(bool(execution_token))),
        VisualPill("Positions", str(len(positions_rows)), "muted"),
        VisualPill("Orders", str(len(orders_rows)), "muted"),
        VisualPill("Max notional", money(limits.get("max_demo_notional_usdt")), "muted"),
    ]
    subtitle = "Demo account control room: connection, account risk, active position state, and scanner candidates."
    st.html(monitor_visual_css())
    st.html(
        build_executive_overview_html(
            status_label=_monitor_status_label(health_error, status_payload),
            subtitle=subtitle,
            pills=pills,
            metrics=metrics,
        )
    )
    st.html(
        build_visual_panels_html(
            position_rows=positions_rows,
            watchlist_rows=scanner_watchlist.head(4).to_dict(orient="records") if not scanner_watchlist.empty else [],
        )
    )


def _pnl_tone(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if parsed > 0:
        return "success"
    if parsed < 0:
        return "negative"
    return "neutral"


def _style_monitor_figure(fig: go.Figure, *, height: int = 250) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=40, b=24),
        font=dict(size=12),
        title_font=dict(size=15),
        xaxis=dict(gridcolor="rgba(127,127,127,.22)", zerolinecolor="rgba(127,127,127,.3)"),
        yaxis=dict(gridcolor="rgba(127,127,127,.22)", zerolinecolor="rgba(127,127,127,.3)"),
        showlegend=False,
    )
    return fig


def _render_monitor_visual_charts(positions_frame: pd.DataFrame, scanner_watchlist: pd.DataFrame) -> None:
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown("**Position PnL**")
        if positions_frame.empty or not {"symbol", "unrealized_pnl"}.issubset(positions_frame.columns):
            st.info("No position PnL chart yet.")
        else:
            chart_df = positions_frame.copy()
            chart_df["unrealized_pnl"] = pd.to_numeric(chart_df["unrealized_pnl"], errors="coerce").fillna(0.0)
            colors = ["#14b8a6" if value >= 0 else "#f43f5e" for value in chart_df["unrealized_pnl"]]
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=chart_df["symbol"].astype(str),
                        y=chart_df["unrealized_pnl"],
                        marker_color=colors,
                        text=chart_df["unrealized_pnl"].map(lambda value: f"${value:,.2f}"),
                        textposition="outside",
                    )
                ]
            )
            fig.update_layout(title="Open Position Unrealized PnL")
            st.plotly_chart(_style_monitor_figure(fig), use_container_width=True)
    with chart_right:
        st.markdown("**Scanner Scores**")
        if scanner_watchlist.empty or not {"symbol", "score"}.issubset(scanner_watchlist.columns):
            st.info("No scanner score chart yet.")
        else:
            chart_df = scanner_watchlist.head(10).copy()
            chart_df["score"] = pd.to_numeric(chart_df["score"], errors="coerce").fillna(0.0)
            fig = px.bar(
                chart_df,
                x="symbol",
                y="score",
                color="mode" if "mode" in chart_df.columns else None,
                title="Latest Scanner Candidate Scores",
                range_y=[0, max(10, float(chart_df["score"].max() or 0))],
                color_discrete_sequence=["#14b8a6", "#3b82f6", "#f59e0b", "#f43f5e"],
            )
            st.plotly_chart(_style_monitor_figure(fig), use_container_width=True)


def validate_connection(api_url: str, execution_token: str) -> tuple[bool, str]:
    api_url = api_url.strip().rstrip("/")
    execution_token = execution_token.strip()
    if not api_url:
        return False, "Backend API URL is required."
    if not execution_token:
        return False, "Execution token is required."

    _, wallet_error = api_json_or_error("/execution/demo/wallet", api_url, token=execution_token)
    if wallet_error:
        return False, f"Connection failed: {wallet_error}"
    return True, "Connected"


def render_connection_screen(default_api_url: str) -> None:
    st.header("Bybit Demo Connection")
    st.caption("Connect once to open the monitor.")
    api_url = st.text_input(
        "Backend API URL",
        value=str(st.session_state.get(API_URL_KEY) or default_api_url).rstrip("/"),
    ).rstrip("/")
    execution_token = st.text_input(
        "Execution token",
        value=str(st.session_state.get(EXECUTION_TOKEN_KEY) or ""),
        type="password",
    )

    if st.button("Connect", type="primary"):
        ok, message = validate_connection(api_url, execution_token)
        if ok:
            mark_connected(st.session_state, api_url=api_url, execution_token=execution_token)
            st.success(message)
            st.rerun()
        else:
            st.error(message)


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
            st.error("Connect with an execution API token before placing a demo test short.")
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

    health_payload, health_error = api_json_or_error("/health", api_url)
    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)
    status_payload = status_payload or {}
    limits = status_payload.get("limits") or {}
    jobs = _safe_jobs(api_url)
    scanner_watchlist = _load_scanner_watchlist(api_url, jobs)
    decisions_payload, decisions_error = api_json_or_error("/signals/decisions?limit=5", api_url)
    decision_rows = []
    if isinstance(decisions_payload, dict) and isinstance(decisions_payload.get("rows"), list):
        decision_rows = [row for row in decisions_payload["rows"] if isinstance(row, dict)]

    if status_error:
        st.warning(f"Execution status unavailable: {status_error}")

    if health_error:
        st.warning(f"Backend health unavailable: {health_error}")

    if decisions_error:
        st.warning(f"Signal decisions unavailable: {decisions_error}")

    wallet_payload = positions_payload = orders_payload = None
    wallet_error = positions_error = orders_error = None
    positions_rows: list[dict] = []
    orders_rows: list[dict] = []
    wallet_summary = summarize_wallet(None)

    if not execution_token:
        st.info("Connect in Settings to load demo account data.")
    else:
        wallet_payload, wallet_error = api_json_or_error("/execution/demo/wallet", api_url, token=execution_token)
        positions_payload, positions_error = api_json_or_error("/execution/demo/positions", api_url, token=execution_token)
        orders_payload, orders_error = api_json_or_error("/execution/demo/open-orders", api_url, token=execution_token)

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

    positions_frame = _frame_from_rows(positions_rows)

    _render_variant_a_visual_overview(
        health_error=health_error,
        status_payload=status_payload,
        limits=limits,
        execution_token=execution_token,
        wallet_summary=wallet_summary,
        positions_rows=positions_rows,
        orders_rows=orders_rows,
        scanner_watchlist=scanner_watchlist,
    )
    if not execution_token:
        st.info("Connect in Settings to load demo account data.")
    st.markdown(
        build_signal_decisions_panel_html(decision_rows),
        unsafe_allow_html=True,
    )
    _render_monitor_visual_charts(positions_frame, scanner_watchlist)


def render_app_menu() -> str:
    current = normalize_page(st.session_state.get(SELECTED_PAGE_KEY))
    index = NAV_PAGES.index(current) if current in NAV_PAGES else 0
    selected_page = st.radio(
        "Monitor / Reports / Scanner Jobs / Signal Decisions / Execution History / Settings",
        NAV_PAGES,
        index=index,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state[SELECTED_PAGE_KEY] = normalize_page(selected_page)
    return normalize_page(selected_page)


def render_monitor_page(api_url: str, execution_token: str, auto_refresh: bool) -> None:
    render_bot_monitor(api_url, execution_token)


def render_reports_page(api_url: str, auto_refresh: bool) -> None:
    st.header("Reports")
    st.caption("Backtest summaries, optimizer results and historical result charts.")
    render_jobs_table(api_url, auto_refresh=False, show_results=True)


def render_signal_decisions_page(api_url: str, execution_token: str) -> None:
    st.header("Signal Decisions")
    c1, c2, c3 = st.columns(3)
    if c1.button("Evaluate latest", type="primary"):
        try:
            response = api_post(
                "/signals/evaluate-latest",
                {"max_candidates": 20, "notify": True},
                api_url,
                token=execution_token,
            )
            st.success("Latest candidates evaluated.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Signal evaluation failed: {_safe_error(exc, execution_token)}")

    if c2.button("Dry-run auto-entry"):
        try:
            response = api_post(
                "/signals/demo-auto-entry",
                {"max_candidates": 20, "notify": True, "dry_run": True},
                api_url,
                token=execution_token,
            )
            st.success("Dry-run auto-entry evaluated.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Dry-run auto-entry failed: {_safe_error(exc, execution_token)}")

    if c3.button("Demo auto-entry"):
        try:
            response = api_post(
                "/signals/demo-auto-entry",
                {"max_candidates": 20, "notify": True, "dry_run": False},
                api_url,
                token=execution_token,
            )
            st.success("Demo auto-entry completed.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Demo auto-entry failed: {_safe_error(exc, execution_token)}")

    payload, error = api_json_or_error("/signals/decisions?limit=100", api_url)
    if error:
        st.warning(f"Signal decisions unavailable: {error}")
        return
    rows = payload.get("rows") if isinstance(payload, dict) else []
    frame = _frame_from_rows(rows)
    if frame.empty:
        st.info("No signal decisions yet.")
        return
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _job_sort_value(job: dict) -> str:
    return str(job.get("updated_at") or job.get("created_at") or "")


def _job_count(meta: dict, *keys: str) -> Any:
    for key in keys:
        value = meta.get(key)
        if value not in (None, ""):
            return value
    return 0


def _select_lifecycle_job(jobs: list[dict]) -> dict | None:
    job_rows = [job for job in jobs if isinstance(job, dict) and job.get("job_id")]
    if not job_rows:
        return None

    active_rows = [job for job in job_rows if job.get("status") in ACTIVE_STATUSES]
    if active_rows:
        return max(active_rows, key=_job_sort_value)

    selected_from_state = st.session_state.get("selected_job_id")
    for job in job_rows:
        if job.get("job_id") == selected_from_state:
            return job

    return max(job_rows, key=_job_sort_value)


def render_latest_job_candidates(api_url: str, meta: dict) -> None:
    st.markdown("**Latest candidates**")
    job_id = meta.get("job_id")
    job_type = meta.get("job_type") or "scan"
    status = meta.get("status")
    if not job_id:
        st.info("No scanner candidates yet.")
        return
    if job_type == "tp_sl_grid":
        st.info("Optimizer jobs do not produce scanner candidates.")
        return
    if status != "done":
        st.info("Candidates appear here when this scanner job writes result files.")
        return

    try:
        if job_type == "causal_scan":
            signals = csv_to_frame(api_get(f"/jobs/{job_id}/signals.csv", api_url).text)
            evaluations = csv_to_frame(api_get(f"/jobs/{job_id}/evaluations.csv", api_url).text)
            watchlist = build_scanner_watchlist(job_type, signals=signals, evaluations=evaluations, max_rows=8)
        else:
            trades = csv_to_frame(api_get(f"/jobs/{job_id}/trades.csv", api_url).text)
            watchlist = build_scanner_watchlist(job_type, trades=trades, max_rows=8)
    except Exception as exc:
        st.info(f"Candidates are not available yet: {exc}")
        return

    if watchlist.empty:
        st.info("No scanner candidates yet.")
        return

    display_columns = [
        column
        for column in [
            "symbol",
            "mode",
            "score",
            "status",
            "price",
            "turnover_usdt",
            "outcome",
            "pnl_underlying_pct",
            "time_utc",
        ]
        if column in watchlist.columns
    ]
    st.dataframe(watchlist[display_columns], use_container_width=True, hide_index=True)


def _progress_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def render_job_progress(meta: dict) -> None:
    progress = meta.get("progress") if isinstance(meta.get("progress"), dict) else {}
    processed = _progress_int(progress.get("processed"))
    total = _progress_int(progress.get("total"))

    if total > 0:
        ratio = min(max(processed / total, 0.0), 1.0)
        st.progress(ratio, text=f"{processed} / {total} symbol-days")
    else:
        st.caption("Progress will appear after the scanner starts processing symbol-days.")

    current_symbol = progress.get("current_symbol") or "n/a"
    current_date = progress.get("current_date") or "n/a"
    st.markdown("**Now scanning**")
    st.caption(f"{current_symbol} | {current_date}")

    st.markdown("**Cache**")
    cache_cols = st.columns(4)
    cache_cols[0].metric("Hits", progress.get("cache_hits") or 0)
    cache_cols[1].metric("Downloads", progress.get("downloads") or 0)
    cache_cols[2].metric("Missing", progress.get("missing_files") or 0)
    cache_cols[3].metric("Errors", progress.get("errors") or 0)

    warnings = meta.get("warnings") if isinstance(meta.get("warnings"), list) else []
    if warnings:
        st.markdown("**Warnings**")
        warning_rows = [row for row in warnings if isinstance(row, dict)]
        for warning in warning_rows[:5]:
            symbol = warning.get("symbol") or "unknown"
            date = warning.get("date") or "unknown"
            message = warning.get("message") or "warning"
            st.warning(f"{symbol} {date}: {message}")


def render_active_job_overview(api_url: str, jobs: list[dict], *, auto_refresh: bool) -> dict | None:
    st.subheader("Active Job")
    selected_row = _select_lifecycle_job(jobs)
    if not selected_row:
        st.info("No scanner jobs yet. Start a scan to see its lifecycle here.")
        return None

    selected_job = selected_row["job_id"]
    try:
        loaded_meta = api_get(f"/jobs/{selected_job}", api_url).json()
        meta = loaded_meta if isinstance(loaded_meta, dict) else {}
    except Exception as exc:
        st.warning(f"Failed to load active job details: {exc}")
        meta = {}

    meta = {**selected_row, **meta}
    meta["job_id"] = selected_job
    st.session_state["selected_job_id"] = selected_job

    with st.container(border=True):
        cols = st.columns(6)
        cols[0].metric("Status", meta.get("status") or "unknown")
        cols[1].metric("Type", meta.get("job_type") or "scan")
        cols[2].metric("Metrics rows", _job_count(meta, "metrics_rows", "grid_rows"))
        cols[3].metric("Signals", _job_count(meta, "signals_rows"))
        cols[4].metric("Trades", _job_count(meta, "trades_rows", "evaluations_rows", "grid_trades_rows"))
        cols[5].metric("Updated", (meta.get("updated_at") or "")[:19] or "n/a")
        render_job_status(meta)
        render_job_progress(meta)
        if meta.get("status") in ACTIVE_STATUSES and auto_refresh:
            st.caption("Auto-refreshing while this job is active.")
        render_latest_job_candidates(api_url, meta)

    return meta


def render_selected_job_results(api_url: str, selected_job: str, *, auto_refresh: bool) -> None:
    """Render metadata, status, downloads, tables and charts for one selected job."""
    try:
        meta = api_get(f"/jobs/{selected_job}", api_url).json()
    except Exception as exc:
        st.error(f"Failed to load selected job: {exc}")
        return

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


def render_jobs_table(
    api_url: str,
    *,
    auto_refresh: bool,
    show_results: bool,
    jobs: list[dict] | None = None,
) -> str | None:
    st.header("Jobs")
    try:
        if jobs is None:
            jobs = api_get("/jobs", api_url).json()
        if not jobs:
            st.info("No jobs yet. Start a scan from Scanner Jobs.")
            return None

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

        job_ids = jobs_df["job_id"].tolist() if "job_id" in jobs_df.columns else []
        if not job_ids:
            st.info("No jobs yet. Start a scan from Scanner Jobs.")
            return None

        selected_from_state = st.session_state.get("selected_job_id")
        default_index = job_ids.index(selected_from_state) if selected_from_state in job_ids else 0
        selected_job = st.selectbox("Open job", job_ids, index=default_index)
        st.session_state["selected_job_id"] = selected_job
    except Exception as exc:
        st.warning(f"Backend is not reachable yet: {exc}")
        return None

    if show_results and selected_job:
        render_selected_job_results(api_url, selected_job, auto_refresh=auto_refresh)

    return selected_job


def render_scanner_jobs_page(api_url: str, auto_refresh: bool) -> None:
    st.header("Scanner Jobs")
    active_jobs_auto_refresh = st.checkbox("Auto-refresh active jobs", value=auto_refresh)
    with st.expander("Scan settings", expanded=True):
        job_mode = st.radio("Job type", ["Archive scan", "Causal signal scan", "TP/SL optimizer"], horizontal=True)
        c1, c2 = st.columns(2)
        start = c1.text_input("Start date", "2026-03-18")
        end = c2.text_input("End date", "2026-03-27")
        symbols_raw = st.text_area(
            "Symbols",
            "EIGENUSDT,GRASSUSDT,RVNUSDT,ENJUSDT,JTOUSDT,STGUSDT,ENAUSDT",
            height=100,
        )
        c3, c4, c5 = st.columns(3)
        full_universe = c3.checkbox("Full archive universe", value=False)
        max_symbols = c4.number_input("Max symbols", min_value=0, max_value=2000, value=0, step=10)
        min_turnover = c5.number_input("Min turnover USDT", min_value=0, value=1_000_000, step=250_000)
        c6, c7 = st.columns(2)
        weak_threshold = c6.slider("Weak threshold", 0, 15, 9)
        pump_threshold = c7.slider("Pump threshold", 0, 15, 9)
        c8, c9, c10, c11 = st.columns(4)
        tp_weak = c8.number_input(
            "TP weak underlying",
            value=0.06,
            min_value=0.001,
            max_value=1.0,
            step=0.01,
            format="%.3f",
        )
        sl_weak = c9.number_input(
            "SL weak underlying",
            value=0.07,
            min_value=0.001,
            max_value=1.0,
            step=0.01,
            format="%.3f",
        )
        tp_pump = c10.number_input(
            "TP pump underlying",
            value=0.08,
            min_value=0.001,
            max_value=1.0,
            step=0.01,
            format="%.3f",
        )
        sl_pump = c11.number_input(
            "SL pump underlying",
            value=0.07,
            min_value=0.001,
            max_value=1.0,
            step=0.01,
            format="%.3f",
        )
        max_hold_min = st.number_input("Max hold minutes", min_value=15, max_value=1440, value=720, step=15)
        if job_mode == "TP/SL optimizer":
            grid_cols = st.columns(2)
            tp_grid_raw = grid_cols[0].text_input("TP grid", "0.04,0.06,0.08")
            sl_grid_raw = grid_cols[1].text_input("SL grid", "0.05,0.07")
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

    jobs = _safe_jobs(api_url)
    active_meta = render_active_job_overview(api_url, jobs, auto_refresh=active_jobs_auto_refresh)
    render_jobs_table(api_url, auto_refresh=False, show_results=True, jobs=jobs)
    if active_jobs_auto_refresh and active_meta and active_meta.get("status") in ACTIVE_STATUSES:
        time.sleep(3)
        st.rerun()


def render_execution_history_page(api_url: str, execution_token: str) -> None:
    st.header("Execution History")
    if not execution_token.strip():
        st.info("Reconnect with an execution API token to view the execution journal.")
        return

    journal_payload, journal_error = api_json_or_error(
        "/execution/demo/journal?limit=100",
        api_url,
        token=execution_token,
    )
    if journal_error:
        st.warning(f"Execution history unavailable: {journal_error}")
        return

    journal_frame = _frame_from_rows(_journal_rows(journal_payload))
    if journal_frame.empty:
        st.info("No execution history rows.")
        return

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


def render_settings_page(api_url: str, execution_token: str) -> None:
    st.header("Settings")
    flash_message = st.session_state.pop("settings_reconnect_flash", None)
    if flash_message:
        st.success(str(flash_message))
    st.caption("Connection settings are session-local and are not written to disk.")

    new_api_url = st.text_input("Backend API URL", value=api_url.rstrip("/")).strip().rstrip("/")
    new_execution_token = st.text_input(
        "Execution token",
        value="",
        type="password",
        help="Leave blank to keep the current session token.",
    ).strip()

    if st.button("Reconnect", type="primary"):
        token_to_use = new_execution_token or execution_token.strip()
        ok, message = validate_connection(new_api_url, token_to_use)
        if ok:
            mark_connected(st.session_state, api_url=new_api_url, execution_token=token_to_use)
            st.session_state[SELECTED_PAGE_KEY] = "Settings"
            st.session_state["settings_reconnect_flash"] = "Connection updated."
            st.rerun()
        else:
            st.error(message)

    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)
    status_for_display = status_payload if isinstance(status_payload, dict) else {}
    if status_error:
        st.warning(f"Execution demo status unavailable: {status_error}")
    else:
        safe_status = {
            key: status_for_display.get(key)
            for key in ["mode", "enabled", "configured", "limits", "api_token_configured"]
            if key in status_for_display
        }
        st.json(safe_status)

    st.subheader("Telegram")
    telegram_payload, telegram_error = api_json_or_error("/signals/telegram/status", api_url)
    if telegram_error:
        st.warning(f"Telegram status unavailable: {telegram_error}")
    else:
        st.json(telegram_payload)
    if st.button("Send Telegram test message"):
        try:
            response = api_post("/signals/telegram/test", {}, api_url, token=execution_token)
            st.success("Telegram test requested.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Telegram test failed: {_safe_error(exc, execution_token)}")

    with st.expander("Controlled demo test short", expanded=False):
        render_demo_test_short_form(api_url, execution_token, status_for_display)


ensure_navigation_state(st.session_state, default_api_url=DEFAULT_API)

if not is_connected(st.session_state):
    render_connection_screen(DEFAULT_API)
    st.stop()

connection = connection_values(st.session_state)
api_url = connection["api_url"]
execution_token = connection["execution_token"]
auto_refresh = True

menu_col, action_col = st.columns([1, 0.18])
with menu_col:
    page = render_app_menu()
with action_col:
    if st.button("Disconnect"):
        disconnect(st.session_state)
        st.rerun()

if page == "Monitor":
    render_monitor_page(api_url, execution_token, auto_refresh)
elif page == "Reports":
    render_reports_page(api_url, auto_refresh)
elif page == "Scanner Jobs":
    render_scanner_jobs_page(api_url, auto_refresh)
elif page == "Signal Decisions":
    render_signal_decisions_page(api_url, execution_token)
elif page == "Execution History":
    render_execution_history_page(api_url, execution_token)
elif page == "Settings":
    render_settings_page(api_url, execution_token)

st.stop()
