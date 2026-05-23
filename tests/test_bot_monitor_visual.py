from __future__ import annotations

from ui.bot_monitor_visual import (
    VisualMetric,
    VisualPill,
    build_executive_overview_html,
    build_signal_decisions_panel_html,
    build_visual_panels_html,
)


def test_executive_overview_html_renders_variant_a_structure() -> None:
    html = build_executive_overview_html(
        status_label="DEMO CONNECTED",
        subtitle="Reads demo account state.",
        pills=[
            VisualPill("Backend", "online", "success"),
            VisualPill("Execution", "enabled", "warning"),
        ],
        metrics=[
            VisualMetric("Equity", "$1,024.80"),
            VisualMetric("Unreal PnL", "-$0.42", "negative"),
            VisualMetric("Margin", "$6.68"),
            VisualMetric("Signals", "7 waiting", "accent"),
        ],
    )

    assert "bwi-executive-overview" in html
    assert "bwi-status-badge bwi-tone-success" in html
    assert "DEMO CONNECTED" in html
    assert html.index("Equity") < html.index("Unreal PnL")
    assert html.count("bwi-kpi-card") == 4


def test_visual_panels_html_renders_position_and_watchlist_cards() -> None:
    html = build_visual_panels_html(
        position_rows=[
            {
                "symbol": "ENAUSDT",
                "side": "Sell",
                "size": 95,
                "entry_price": 0.10441,
                "mark_price": 0.10485,
                "unrealized_pnl": -0.42,
                "pnl_pct": -0.004,
                "leverage": 5,
                "take_profit": 0.09814,
                "stop_loss": 0.11172,
            }
        ],
        watchlist_rows=[
            {
                "symbol": "JTOUSDT",
                "mode": "pump",
                "score": 10,
                "status": "waiting",
                "price": 2.5,
                "turnover_usdt": 1_500_000,
            }
        ],
    )

    assert "bwi-panel-grid" in html
    assert "bwi-position-primary" in html
    assert "bwi-position-metrics" in html
    assert "Open Positions" in html
    assert "Scanner Watchlist" in html
    assert "ENAUSDT" in html
    assert "TP / SL" in html
    assert "0.09814 / 0.11172" in html
    assert "JTOUSDT" in html
    assert "score 10" in html


def test_visual_css_balances_large_monitor_layout() -> None:
    from ui.bot_monitor_visual import monitor_visual_css

    css = monitor_visual_css()

    assert ".bwi-kpi-grid" in css
    assert "grid-template-columns: repeat(4, minmax(160px, 1fr))" in css
    assert ".bwi-position-primary" in css
    assert ".bwi-position-metrics" in css
    assert "grid-template-columns: minmax(0, 1.12fr) minmax(320px, .88fr)" in css


def test_visual_css_uses_streamlit_theme_surfaces() -> None:
    from ui.bot_monitor_visual import monitor_visual_css

    css = monitor_visual_css()

    assert "var(--background-color)" in css
    assert "var(--text-color)" in css
    assert "--bwi-surface-soft" in css
    assert "--bwi-border" in css
    for dark_color in ["#101418", "#151a1f", "#26313c", "#2b3743", "#1f2933", "#2f3b48"]:
        assert dark_color not in css


def test_visual_html_escapes_dynamic_values() -> None:
    html = build_executive_overview_html(
        status_label="<script>alert(1)</script>",
        subtitle="<b>unsafe</b>",
        pills=[VisualPill("<img src=x>", "<script>bad()</script>", "success")],
        metrics=[VisualMetric("<b>Equity</b>", "<script>bad()</script>")],
    )

    assert "<script" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;Equity&lt;/b&gt;" in html


def test_signal_decisions_panel_renders_latest_decisions() -> None:
    html = build_signal_decisions_panel_html(
        [
            {
                "symbol": "ENAUSDT",
                "status": "qualified",
                "reason": "qualified",
                "telegram_status": "sent",
                "order_link_id": "",
            },
            {
                "symbol": "JTOUSDT",
                "status": "skipped",
                "reason": "dry_run",
                "telegram_status": "sent",
                "order_link_id": "",
            },
        ]
    )

    assert "Signal Decisions" in html
    assert "ENAUSDT" in html
    assert "qualified" in html
    assert "JTOUSDT" in html
    assert "dry_run" in html
    assert "Telegram sent" in html
    assert "bwi-tone-success" in html
    assert "bwi-tone-muted" in html


def test_signal_decisions_panel_renders_empty_state() -> None:
    html = build_signal_decisions_panel_html([])

    assert "Signal Decisions" in html
    assert "No signal decisions yet." in html


def test_signal_decisions_panel_escapes_dynamic_values() -> None:
    html = build_signal_decisions_panel_html(
        [
            {
                "symbol": "<script>alert(1)</script>",
                "status": "<b>error</b>",
                "reason": "<img src=x>",
                "telegram_status": "sent<script>",
                "order_link_id": "<svg>",
            }
        ]
    )

    assert "<script" not in html
    assert "<img" not in html
    assert "<svg" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x&gt;" in html
