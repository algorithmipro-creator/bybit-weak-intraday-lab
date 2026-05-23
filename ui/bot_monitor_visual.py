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
.bwi-executive-overview,
.bwi-panel-grid,
.bwi-signal-decisions-panel {
  --bwi-surface: var(--background-color);
  --bwi-surface-soft: rgba(127, 127, 127, .07);
  --bwi-surface-strong: rgba(127, 127, 127, .11);
  --bwi-border: rgba(127, 127, 127, .24);
  --bwi-border-strong: rgba(127, 127, 127, .34);
  --bwi-text: var(--text-color);
  --bwi-text-muted: var(--text-color);
}
.bwi-executive-overview {
  background: var(--bwi-surface);
  border: 1px solid var(--bwi-border);
  border-radius: 8px;
  color: var(--bwi-text);
  padding: 15px;
  margin: 6px 0 12px;
  box-shadow: 0 10px 22px rgba(0,0,0,.08);
}
.bwi-monitor-top {
  align-items: flex-start;
  display: flex;
  gap: 14px;
  justify-content: space-between;
  margin-bottom: 10px;
}
.bwi-monitor-title {
  font-size: 18px;
  font-weight: 720;
  line-height: 1.2;
  margin: 0 0 3px;
}
.bwi-monitor-subtitle {
  color: var(--bwi-text-muted);
  font-size: 12px;
  line-height: 1.35;
  margin: 0;
  opacity: .68;
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
.bwi-status-badge { border: 1px solid var(--bwi-border); }
.bwi-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 12px;
}
.bwi-pill span:first-child {
  color: var(--bwi-text-muted);
  font-weight: 650;
  opacity: .72;
}
.bwi-kpi-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
}
.bwi-kpi-card,
.bwi-panel {
  background: var(--bwi-surface-soft);
  border: 1px solid var(--bwi-border);
  border-radius: 8px;
}
.bwi-kpi-card {
  min-height: 76px;
  padding: 12px;
}
.bwi-kpi-label,
.bwi-panel-label,
.bwi-row-meta {
  color: var(--bwi-text-muted);
  font-size: 12px;
  opacity: .66;
}
.bwi-kpi-value {
  color: var(--bwi-text);
  font-size: 20px;
  font-weight: 760;
  line-height: 1.15;
  margin-top: 7px;
  overflow-wrap: anywhere;
}
.bwi-kpi-detail {
  color: var(--bwi-text-muted);
  font-size: 12px;
  margin-top: 6px;
  opacity: .62;
}
.bwi-panel-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1.12fr) minmax(320px, .88fr);
  margin: 0 0 12px;
}
.bwi-panel {
  color: var(--bwi-text);
  min-height: 156px;
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
  background: var(--bwi-surface);
  border: 1px solid var(--bwi-border);
  border-radius: 8px;
  padding: 10px;
}
.bwi-position-primary {
  padding: 13px;
}
.bwi-position-metrics {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 11px;
}
.bwi-position-metric {
  background: var(--bwi-surface-strong);
  border: 1px solid var(--bwi-border);
  border-radius: 8px;
  min-height: 54px;
  padding: 8px;
}
.bwi-position-metric span {
  color: var(--bwi-text-muted);
  display: block;
  font-size: 11px;
  margin-bottom: 4px;
  opacity: .62;
}
.bwi-position-metric strong {
  color: var(--bwi-text);
  display: block;
  font-size: 13px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}
.bwi-row-main {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}
.bwi-symbol {
  color: var(--bwi-text);
  font-size: 14px;
  font-weight: 760;
}
.bwi-chip {
  background: var(--bwi-surface-strong);
  border: 1px solid var(--bwi-border-strong);
  border-radius: 999px;
  color: var(--bwi-text);
  font-size: 11px;
  font-weight: 650;
  padding: 4px 8px;
}
.bwi-row-detail {
  color: var(--bwi-text-muted);
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 8px 12px;
  margin-top: 8px;
  opacity: .74;
}
.bwi-empty {
  align-items: center;
  border: 1px dashed var(--bwi-border-strong);
  border-radius: 8px;
  color: var(--bwi-text-muted);
  display: flex;
  font-size: 13px;
  min-height: 104px;
  padding: 12px;
  opacity: .7;
}
.bwi-tone-success { background: rgba(20, 184, 166, .16); color: #0f766e; }
.bwi-tone-warning { background: rgba(245, 158, 11, .16); color: #92400e; }
.bwi-tone-negative { background: rgba(244, 63, 94, .16); color: #be123c; }
.bwi-tone-accent { background: rgba(59, 130, 246, .16); color: #1d4ed8; }
.bwi-tone-muted { background: var(--bwi-surface-strong); color: var(--bwi-text); }
.bwi-tone-neutral { background: var(--bwi-surface-soft); color: var(--bwi-text); }
.bwi-kpi-card.bwi-tone-success,
.bwi-kpi-card.bwi-tone-warning,
.bwi-kpi-card.bwi-tone-negative,
.bwi-kpi-card.bwi-tone-accent,
.bwi-kpi-card.bwi-tone-muted,
.bwi-kpi-card.bwi-tone-neutral {
  background: var(--bwi-surface-soft);
}
.bwi-kpi-card.bwi-tone-success .bwi-kpi-value { color: #0f766e; }
.bwi-kpi-card.bwi-tone-warning .bwi-kpi-value { color: #92400e; }
.bwi-kpi-card.bwi-tone-negative .bwi-kpi-value { color: #be123c; }
.bwi-kpi-card.bwi-tone-accent .bwi-kpi-value { color: #1d4ed8; }
@media (prefers-color-scheme: dark) {
  .bwi-executive-overview,
  .bwi-panel-grid,
  .bwi-signal-decisions-panel {
    --bwi-surface-soft: rgba(255, 255, 255, .055);
    --bwi-surface-strong: rgba(255, 255, 255, .085);
    --bwi-border: rgba(255, 255, 255, .13);
    --bwi-border-strong: rgba(255, 255, 255, .2);
  }
  .bwi-tone-success { color: #7dd3c7; }
  .bwi-tone-warning { color: #fbbf24; }
  .bwi-tone-negative { color: #fb7185; }
  .bwi-tone-accent { color: #93c5fd; }
  .bwi-kpi-card.bwi-tone-success .bwi-kpi-value { color: #7dd3c7; }
  .bwi-kpi-card.bwi-tone-warning .bwi-kpi-value { color: #fbbf24; }
  .bwi-kpi-card.bwi-tone-negative .bwi-kpi-value { color: #fb7185; }
  .bwi-kpi-card.bwi-tone-accent .bwi-kpi-value { color: #93c5fd; }
}
@media (max-width: 900px) {
  .bwi-monitor-top { display: block; }
  .bwi-status-badge { margin-top: 10px; }
  .bwi-kpi-grid,
  .bwi-panel-grid { grid-template-columns: 1fr; }
  .bwi-position-metrics { grid-template-columns: 1fr; }
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


def build_signal_decisions_panel_html(decision_rows: list[dict]) -> str:
    return (
        '<div class="bwi-signal-decisions-panel">'
        f'{_panel_html("Signal Decisions", _signal_decision_rows_html(decision_rows), "No signal decisions yet.")}'
        "</div>"
    )


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
    for index, row in enumerate(rows[:3]):
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
        if index == 0:
            parts.append(
                '<div class="bwi-list-row bwi-position-primary">'
                '<div class="bwi-row-main">'
                f'<div class="bwi-symbol">{escape(symbol)}</div>'
                f'<div class="bwi-chip">{escape(side)} {escape(size)} | Lev {escape(leverage)}x</div>'
                '</div>'
                '<div class="bwi-position-metrics">'
                f'<div class="bwi-position-metric"><span>Entry / Mark</span><strong>{escape(entry)} -> {escape(mark)}</strong></div>'
                f'<div class="bwi-position-metric"><span>PnL</span><strong>{escape(pnl)} {escape(pnl_pct)}</strong></div>'
                f'<div class="bwi-position-metric"><span>TP / SL</span><strong>{escape(take_profit)} / {escape(stop_loss)}</strong></div>'
                '</div></div>'
            )
        else:
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


def _signal_decision_rows_html(rows: list[dict]) -> str:
    parts = []
    for row in rows[:5]:
        symbol = _value(row.get("symbol"))
        status = _value(row.get("status"))
        reason = _value(row.get("reason"))
        telegram_status = _value(row.get("telegram_status"))
        detail_parts = [
            f"<span>{escape(reason)}</span>",
            f"<span>Telegram {escape(telegram_status)}</span>",
        ]
        execution_status = row.get("execution_status")
        order_link_id = row.get("order_link_id")
        if execution_status is not None and execution_status != "":
            detail_parts.append(f"<span>{escape(_value(execution_status))}</span>")
        if order_link_id is not None and order_link_id != "":
            detail_parts.append(f"<span>{escape(_value(order_link_id))}</span>")

        parts.append(
            '<div class="bwi-list-row">'
            '<div class="bwi-row-main">'
            f'<div class="bwi-symbol">{escape(symbol)}</div>'
            f'<div class="bwi-chip {_tone_class(_signal_decision_tone(status))}">{escape(status)}</div>'
            '</div>'
            f'<div class="bwi-row-detail">{"".join(detail_parts)}</div>'
            '</div>'
        )
    return "".join(parts)


def _signal_decision_tone(status: str) -> str:
    normalized = status.lower()
    if normalized in {"qualified", "entered"}:
        return "success"
    if normalized == "error":
        return "negative"
    if normalized == "skipped":
        return "muted"
    return "neutral"


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
