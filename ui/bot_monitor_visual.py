from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any


@dataclass(frozen=True)
class VisualMetric:
    label: str
    value: str
    tone: str = "neutral"
    detail: str = ""


@dataclass(frozen=True)
class VisualPill:
    label: str
    value: str
    tone: str = "neutral"


TONE_CLASS = {
    "success": "bwi-tone-success",
    "warning": "bwi-tone-warning",
    "negative": "bwi-tone-negative",
    "accent": "bwi-tone-accent",
    "muted": "bwi-tone-muted",
    "neutral": "bwi-tone-neutral",
}


def monitor_visual_css() -> str:
    return """
<style>
.bwi-executive-overview {
  background: #101418;
  border: 1px solid #26313c;
  border-radius: 8px;
  color: #e5e7eb;
  padding: 18px;
  margin: 8px 0 16px;
  box-shadow: 0 12px 28px rgba(0,0,0,.18);
}
.bwi-monitor-top {
  align-items: flex-start;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 14px;
}
.bwi-monitor-title {
  font-size: 21px;
  font-weight: 720;
  line-height: 1.2;
  margin: 0 0 4px;
}
.bwi-monitor-subtitle {
  color: #9aa5b1;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
}
.bwi-status-badge,
.bwi-pill {
  border-radius: 999px;
  display: inline-flex;
  font-size: 11px;
  font-weight: 720;
  gap: 6px;
  letter-spacing: .02em;
  line-height: 1;
  padding: 8px 10px;
  text-transform: uppercase;
  white-space: nowrap;
}
.bwi-status-badge { border: 1px solid rgba(255,255,255,.08); }
.bwi-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0 14px;
}
.bwi-pill span:first-child {
  color: rgba(229,231,235,.68);
  font-weight: 650;
}
.bwi-kpi-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.bwi-kpi-card,
.bwi-panel {
  background: #151a1f;
  border: 1px solid #2b3743;
  border-radius: 8px;
}
.bwi-kpi-card {
  min-height: 84px;
  padding: 12px;
}
.bwi-kpi-label,
.bwi-panel-label,
.bwi-row-meta {
  color: #9aa5b1;
  font-size: 12px;
}
.bwi-kpi-value {
  color: #f8fafc;
  font-size: 22px;
  font-weight: 760;
  line-height: 1.15;
  margin-top: 8px;
  overflow-wrap: anywhere;
}
.bwi-kpi-detail {
  color: #87929f;
  font-size: 12px;
  margin-top: 7px;
}
.bwi-panel-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  margin: 0 0 16px;
}
.bwi-panel {
  color: #e5e7eb;
  min-height: 168px;
  padding: 14px;
}
.bwi-panel-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}
.bwi-panel-title {
  font-size: 15px;
  font-weight: 720;
}
.bwi-list {
  display: grid;
  gap: 8px;
}
.bwi-list-row {
  background: #101418;
  border: 1px solid #26313c;
  border-radius: 8px;
  padding: 10px;
}
.bwi-row-main {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}
.bwi-symbol {
  color: #f8fafc;
  font-size: 14px;
  font-weight: 760;
}
.bwi-chip {
  background: #1f2933;
  border: 1px solid #2f3b48;
  border-radius: 999px;
  color: #cbd5e1;
  font-size: 11px;
  font-weight: 650;
  padding: 4px 8px;
}
.bwi-row-detail {
  color: #c4ccd5;
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 8px 12px;
  margin-top: 8px;
}
.bwi-empty {
  align-items: center;
  border: 1px dashed #344252;
  border-radius: 8px;
  color: #9aa5b1;
  display: flex;
  font-size: 13px;
  min-height: 104px;
  padding: 12px;
}
.bwi-tone-success { background: rgba(20, 184, 166, .16); color: #7dd3c7; }
.bwi-tone-warning { background: rgba(245, 158, 11, .15); color: #fbbf24; }
.bwi-tone-negative { background: rgba(244, 63, 94, .15); color: #fb7185; }
.bwi-tone-accent { background: rgba(59, 130, 246, .15); color: #93c5fd; }
.bwi-tone-muted { background: rgba(148, 163, 184, .12); color: #cbd5e1; }
.bwi-tone-neutral { background: rgba(255,255,255,.06); color: #e5e7eb; }
.bwi-kpi-card.bwi-tone-success,
.bwi-kpi-card.bwi-tone-warning,
.bwi-kpi-card.bwi-tone-negative,
.bwi-kpi-card.bwi-tone-accent,
.bwi-kpi-card.bwi-tone-muted,
.bwi-kpi-card.bwi-tone-neutral {
  background: #151a1f;
}
.bwi-kpi-card.bwi-tone-success .bwi-kpi-value { color: #7dd3c7; }
.bwi-kpi-card.bwi-tone-warning .bwi-kpi-value { color: #fbbf24; }
.bwi-kpi-card.bwi-tone-negative .bwi-kpi-value { color: #fb7185; }
.bwi-kpi-card.bwi-tone-accent .bwi-kpi-value { color: #93c5fd; }
@media (max-width: 900px) {
  .bwi-monitor-top { display: block; }
  .bwi-status-badge { margin-top: 10px; }
  .bwi-kpi-grid,
  .bwi-panel-grid { grid-template-columns: 1fr; }
}
</style>
"""


def build_executive_overview_html(
    *,
    status_label: str,
    subtitle: str,
    pills: list[VisualPill],
    metrics: list[VisualMetric],
) -> str:
    pill_html = "".join(_pill_html(pill) for pill in pills)
    metric_html = "".join(_metric_html(metric) for metric in metrics)
    status_class = _tone_class("success" if "connected" in status_label.lower() or "online" in status_label.lower() else "warning")
    return f"""
<div class="bwi-executive-overview">
  <div class="bwi-monitor-top">
    <div>
      <div class="bwi-monitor-title">Bot Monitor</div>
      <p class="bwi-monitor-subtitle">{escape(subtitle)}</p>
    </div>
    <div class="bwi-status-badge {status_class}">{escape(status_label)}</div>
  </div>
  <div class="bwi-pill-row">{pill_html}</div>
  <div class="bwi-kpi-grid">{metric_html}</div>
</div>
"""


def build_visual_panels_html(*, position_rows: list[dict], watchlist_rows: list[dict]) -> str:
    return f"""
<div class="bwi-panel-grid">
  {_panel_html("Open Positions", _position_rows_html(position_rows), "No open demo positions.")}
  {_panel_html("Scanner Watchlist", _watchlist_rows_html(watchlist_rows), "No scanner candidates yet.")}
</div>
"""


def _pill_html(pill: VisualPill) -> str:
    return (
        f'<div class="bwi-pill {_tone_class(pill.tone)}">'
        f"<span>{escape(pill.label)}</span><strong>{escape(pill.value)}</strong>"
        "</div>"
    )


def _metric_html(metric: VisualMetric) -> str:
    detail = f'<div class="bwi-kpi-detail">{escape(metric.detail)}</div>' if metric.detail else ""
    return (
        f'<div class="bwi-kpi-card {_tone_class(metric.tone)}">'
        f'<div class="bwi-kpi-label">{escape(metric.label)}</div>'
        f'<div class="bwi-kpi-value">{escape(metric.value)}</div>'
        f"{detail}</div>"
    )


def _panel_html(title: str, rows_html: str, empty_text: str) -> str:
    body = f'<div class="bwi-list">{rows_html}</div>' if rows_html else f'<div class="bwi-empty">{escape(empty_text)}</div>'
    return (
        '<div class="bwi-panel">'
        '<div class="bwi-panel-head">'
        f'<div class="bwi-panel-title">{escape(title)}</div>'
        '<div class="bwi-panel-label">live view</div>'
        '</div>'
        f"{body}</div>"
    )


def _position_rows_html(rows: list[dict]) -> str:
    parts = []
    for row in rows[:3]:
        symbol = _value(row.get("symbol"))
        side = _value(row.get("side"))
        size = _value(row.get("size"))
        pnl = _signed_money(row.get("unrealized_pnl"))
        pnl_pct = _pct(row.get("pnl_pct"))
        entry = _value(row.get("entry_price"))
        mark = _value(row.get("mark_price"))
        leverage = _value(row.get("leverage"))
        take_profit = _value(row.get("take_profit"))
        stop_loss = _value(row.get("stop_loss"))
        parts.append(
            '<div class="bwi-list-row">'
            '<div class="bwi-row-main">'
            f'<div class="bwi-symbol">{escape(symbol)}</div>'
            f'<div class="bwi-chip">{escape(side)} {escape(size)}</div>'
            '</div>'
            '<div class="bwi-row-detail">'
            f'<span>Entry {escape(entry)}</span>'
            f'<span>Mark {escape(mark)}</span>'
            f'<span>PnL {escape(pnl)} {escape(pnl_pct)}</span>'
            f'<span>Lev {escape(leverage)}x</span>'
            f'<span>TP {escape(take_profit)}</span>'
            f'<span>SL {escape(stop_loss)}</span>'
            '</div></div>'
        )
    return "".join(parts)


def _watchlist_rows_html(rows: list[dict]) -> str:
    parts = []
    for row in rows[:4]:
        symbol = _value(row.get("symbol"))
        mode = _value(row.get("mode"))
        score = _value(row.get("score"))
        status = _value(row.get("status"))
        price = _value(row.get("price"))
        turnover = _money(row.get("turnover_usdt"))
        parts.append(
            '<div class="bwi-list-row">'
            '<div class="bwi-row-main">'
            f'<div class="bwi-symbol">{escape(symbol)}</div>'
            f'<div class="bwi-chip">score {escape(score)}</div>'
            '</div>'
            '<div class="bwi-row-detail">'
            f'<span>{escape(mode)}</span>'
            f'<span>{escape(status)}</span>'
            f'<span>Price {escape(price)}</span>'
            f'<span>Turnover {escape(turnover)}</span>'
            '</div></div>'
        )
    return "".join(parts)


def _tone_class(tone: str) -> str:
    return TONE_CLASS.get(tone, TONE_CLASS["neutral"])


def _value(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _money(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${parsed:,.0f}"


def _signed_money(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "n/a"
    sign = "+" if parsed > 0 else ""
    return f"{sign}${parsed:,.2f}"


def _pct(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return ""
    sign = "+" if parsed > 0 else ""
    return f"({sign}{parsed * 100:.2f}%)"
