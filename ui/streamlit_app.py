from __future__ import annotations

import os
from io import StringIO

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

DEFAULT_API = os.getenv("BWI_API_URL", "http://backend:8000")

st.set_page_config(page_title="Bybit Weak Intraday Lab", layout="wide")
st.title("Bybit Weak Intraday Lab")
st.caption("Research dashboard for weak-continuation and pump-and-fade Bybit USDT-perp scans. No live orders.")

api_url = st.sidebar.text_input("Backend API URL", DEFAULT_API).rstrip("/")


def api_get(path: str):
    r = requests.get(f"{api_url}{path}", timeout=30)
    r.raise_for_status()
    return r


def api_post(path: str, payload: dict):
    r = requests.post(f"{api_url}{path}", json=payload, timeout=30)
    r.raise_for_status()
    return r


def parse_float_grid(value: str) -> list[float]:
    return [float(x.strip()) for x in value.replace("\n", ",").split(",") if x.strip()]


with st.sidebar:
    st.header("Scan settings")
    job_mode = st.radio("Job type", ["Archive scan", "TP/SL optimizer"], horizontal=True)
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
        if job_mode == "TP/SL optimizer":
            payload["tp_grid"] = parse_float_grid(tp_grid_raw)
            payload["sl_grid"] = parse_float_grid(sl_grid_raw)
            path = "/jobs/optimize-tp-sl"
        resp = api_post(path, payload).json()
        st.success(f"Job queued: {resp['job_id']}")
    except Exception as exc:
        st.error(f"Failed to start job: {exc}")

st.header("Jobs")
try:
    jobs = api_get("/jobs").json()
    if jobs:
        jobs_df = pd.DataFrame(jobs)
        st.dataframe(jobs_df, use_container_width=True)
        selected_job = st.selectbox("Open job", jobs_df["job_id"].tolist())
    else:
        st.info("No jobs yet. Start a scan from the sidebar.")
        selected_job = None
except Exception as exc:
    st.warning(f"Backend is not reachable yet: {exc}")
    selected_job = None

if selected_job:
    meta = api_get(f"/jobs/{selected_job}").json()
    st.subheader(f"Job {selected_job}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", meta.get("status"))
    c2.metric("Metrics rows", meta.get("metrics_rows") or 0)
    c3.metric("Trades rows", meta.get("trades_rows") or 0)
    c4.metric("Updated", (meta.get("updated_at") or "")[:19])
    st.code(meta.get("message") or "", language="text")

    if meta.get("status") == "done" and meta.get("job_type") == "tp_sl_grid":
        grid_csv = api_get(f"/jobs/{selected_job}/grid.csv").text
        grid_trades_csv = api_get(f"/jobs/{selected_job}/grid_trades.csv").text
        grid = pd.read_csv(StringIO(grid_csv)) if grid_csv.strip() else pd.DataFrame()
        grid_trades = pd.read_csv(StringIO(grid_trades_csv)) if grid_trades_csv.strip() else pd.DataFrame()

        tab1, tab2, tab3 = st.tabs(["Grid Summary", "Grid Trades", "Charts"])
        with tab1:
            st.download_button("Download grid CSV", grid_csv, file_name=f"{selected_job}_grid.csv")
            st.dataframe(grid, use_container_width=True)
        with tab2:
            st.download_button("Download grid trades CSV", grid_trades_csv, file_name=f"{selected_job}_grid_trades.csv")
            st.dataframe(grid_trades, use_container_width=True)
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
                st.plotly_chart(px.histogram(grid_trades, x="outcome", color="tp_pct", title="Grid outcomes"), use_container_width=True)
            if grid.empty and grid_trades.empty:
                st.info("No optimizer results in this job.")

    elif meta.get("status") == "done":
        trades_csv = api_get(f"/jobs/{selected_job}/trades.csv").text
        metrics_csv = api_get(f"/jobs/{selected_job}/metrics.csv").text
        trades = pd.read_csv(StringIO(trades_csv)) if trades_csv.strip() else pd.DataFrame()
        metrics = pd.read_csv(StringIO(metrics_csv)) if metrics_csv.strip() else pd.DataFrame()

        tab1, tab2, tab3 = st.tabs(["Trades", "Metrics", "Charts"])
        with tab1:
            st.download_button("Download trades CSV", trades_csv, file_name=f"{selected_job}_trades.csv")
            st.dataframe(trades, use_container_width=True)
        with tab2:
            st.download_button("Download metrics CSV", metrics_csv, file_name=f"{selected_job}_metrics.csv")
            st.dataframe(metrics, use_container_width=True)
        with tab3:
            if not trades.empty:
                left, right = st.columns(2)
                with left:
                    st.plotly_chart(px.bar(trades, x="outcome", title="Outcomes"), use_container_width=True)
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
