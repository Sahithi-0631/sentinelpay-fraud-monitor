"""
SentinelPay — Real-Time Transaction Fraud Monitor.

Single-service institutional risk & fraud operations console modeled after
Stripe Radar, Mercury, and RazorpayX with a light-slate enterprise banking UI.
"""

from __future__ import annotations

import html
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fraud_engine import FraudScoringEngine, HybridStateStore
from graph_builder import build_entity_graph, detect_ring_clusters
from simulator import INDIAN_CITIES, IndianPaymentSimulator, format_inr

st.set_page_config(
    page_title="SentinelPay — Risk & Fraud Operations",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Daylight Enterprise Banking Design System (Stripe Radar / Mercury / RazorpayX)
# ---------------------------------------------------------------------------
BANKING_LIGHT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
    --bg-canvas: #F6F8FA;
    --bg-surface: #FFFFFF;
    --bg-subtle: #F8FAFC;
    --border-hairline: #E2E8F0;
    --border-control: #CBD5E1;
    --text-primary: #0F172A;
    --text-secondary: #475569;
    --text-muted: #64748B;
    --shadow-card: 0 1px 2px rgba(15, 23, 42, 0.04);
}

/* Hide default Streamlit chrome & top colored bar */
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
    display: none !important;
}
[data-testid="stHeader"] {
    background: rgba(246, 248, 250, 0.0) !important;
    height: 2.25rem !important;
}

html, body, .stApp, [data-testid="stAppViewContainer"], [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background-color: var(--bg-canvas) !important;
    color: var(--text-primary) !important;
}

.main .block-container {
    padding-top: 0.85rem !important;
    padding-bottom: 1.25rem !important;
    padding-left: 1.35rem !important;
    padding-right: 1.35rem !important;
    max-width: 100% !important;
}

/* Sidebar Surface */
section[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border-hairline) !important;
}
section[data-testid="stSidebar"] > div {
    background-color: var(--bg-surface) !important;
}
section[data-testid="stSidebar"] .block-container {
    padding: 1rem 0.95rem !important;
}

.mono {
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace !important;
    font-variant-numeric: tabular-nums;
}

/* Top Navigation Header */
.sp-topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    background: var(--bg-surface);
    border: 1px solid var(--border-hairline);
    border-radius: 6px;
    padding: 0.85rem 1.1rem;
    margin-bottom: 0.85rem;
    box-shadow: var(--shadow-card);
}
.sp-brand-row {
    display: flex;
    align-items: baseline;
    gap: 0.65rem;
    flex-wrap: wrap;
}
.sp-brand-title {
    font-size: 1.05rem;
    font-weight: 700;
    letter-spacing: -0.015em;
    color: var(--text-primary);
}
.sp-brand-sub {
    font-size: 0.80rem;
    font-weight: 500;
    color: var(--text-muted);
}
.sp-status-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
}
.sp-sys-pill {
    font-family: 'Inter', sans-serif;
    font-size: 0.74rem;
    font-weight: 500;
    padding: 0.28rem 0.62rem;
    border-radius: 999px;
    border: 1px solid var(--border-hairline);
    background: var(--bg-subtle);
    color: var(--text-secondary);
    white-space: nowrap;
}
.sp-sys-online {
    color: #047857;
    background: #ECFDF5;
    border-color: #A7F3D0;
}
.sp-sys-paused {
    color: #B45309;
    background: #FFFBEB;
    border-color: #FDE68A;
}

/* KPI Strip */
.sp-kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.75rem;
    margin-bottom: 0.85rem;
}
@media (max-width: 1100px) {
    .sp-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.sp-kpi-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-hairline);
    border-radius: 6px;
    padding: 0.85rem 1rem;
    box-shadow: var(--shadow-card);
}
.sp-kpi-label {
    font-size: 0.70rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}
.sp-kpi-value {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 1.32rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
}
.sp-kpi-sub {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-top: 0.35rem;
}

/* Panel Headers */
.sp-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.68rem 0.95rem;
    background: var(--bg-surface);
    border: 1px solid var(--border-hairline);
    border-bottom: 1px solid var(--border-hairline);
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    box-shadow: var(--shadow-card);
}
.sp-panel-title {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    color: var(--text-primary);
    text-transform: uppercase;
}
.sp-panel-meta {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.71rem;
    color: var(--text-muted);
}

/* Pastel Banking Status Pills */
.sp-pill {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: 0.16rem 0.50rem;
    border-radius: 4px;
    white-space: nowrap;
}
.sp-pill-approved {
    background: #ECFDF5;
    color: #047857;
    border: 1px solid #A7F3D0;
}
.sp-pill-flagged {
    background: #FFFBEB;
    color: #B45309;
    border: 1px solid #FDE68A;
}
.sp-pill-blocked {
    background: #FEF2F2;
    color: #B91C1C;
    border: 1px solid #FECACA;
}
.sp-pill-neutral {
    background: #F1F5F9;
    color: #334155;
    border: 1px solid #CBD5E1;
}

/* Live Authorization Ledger Table */
.sp-table-wrap {
    background: var(--bg-surface);
    border: 1px solid var(--border-hairline);
    border-top: none;
    border-bottom-left-radius: 6px;
    border-bottom-right-radius: 6px;
    max-height: 430px;
    overflow-y: auto;
    overflow-x: auto;
    box-shadow: var(--shadow-card);
}
.sp-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.76rem;
}
.sp-table thead th {
    position: sticky;
    top: 0;
    background: #F8FAFC;
    color: #475569;
    font-size: 0.69rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    text-align: left;
    padding: 0.58rem 0.72rem;
    border-bottom: 1px solid #E2E8F0;
    z-index: 2;
    white-space: nowrap;
}
.sp-table tbody tr {
    background: #FFFFFF;
    border-bottom: 1px solid #F1F5F9;
    transition: background-color 0.12s ease;
}
.sp-table tbody tr:hover {
    background-color: #F8FAFC;
}
.sp-table tbody tr.sp-row-selected {
    background-color: #F1F5F9;
    box-shadow: inset 3px 0 0 #0F172A;
}
.sp-table tbody td {
    padding: 0.52rem 0.72rem;
    vertical-align: middle;
    white-space: nowrap;
    color: #0F172A;
}

/* Inspector Card */
.sp-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-hairline);
    border-top: none;
    border-bottom-left-radius: 6px;
    border-bottom-right-radius: 6px;
    padding: 1rem;
    box-shadow: var(--shadow-card);
}
.sp-kv-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.60rem 0.95rem;
    padding: 0.75rem 0;
    border-top: 1px solid var(--border-hairline);
    border-bottom: 1px solid var(--border-hairline);
    margin: 0.70rem 0;
}
.sp-kv-label {
    font-size: 0.67rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    text-transform: uppercase;
}
.sp-kv-val {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.78rem;
    color: var(--text-primary);
    margin-top: 2px;
}

/* Risk Factor Bar */
.sp-factor-row {
    margin-bottom: 0.54rem;
}
.sp-factor-head {
    display: flex;
    justify-content: space-between;
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.71rem;
    color: var(--text-secondary);
    margin-bottom: 3px;
}
.sp-bar-track {
    width: 100%;
    height: 6px;
    background: #F1F5F9;
    border: 1px solid var(--border-hairline);
    border-radius: 3px;
    overflow: hidden;
}
.sp-bar-fill {
    height: 100%;
    border-radius: 2px;
}

/* Sidebar Headings & Clean Secondary Buttons (Zero Blue Buttons) */
.sp-side-section {
    font-size: 0.70rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    text-transform: uppercase;
    margin: 0.9rem 0 0.45rem 0;
    padding-bottom: 0.28rem;
    border-bottom: 1px solid var(--border-hairline);
}
div.stButton > button,
div.stButton > button[kind="secondary"],
div.stButton > button[kind="primary"] {
    background-color: #FFFFFF !important;
    color: #0F172A !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 6px !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    font-size: 0.77rem !important;
    font-weight: 500 !important;
    padding: 0.42rem 0.75rem !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
    transition: background-color 0.14s ease, border-color 0.14s ease !important;
}
div.stButton > button:hover,
div.stButton > button[kind="secondary"]:hover,
div.stButton > button[kind="primary"]:hover {
    background-color: #F1F5F9 !important;
    border-color: #94A3B8 !important;
    color: #0F172A !important;
}
div.stButton > button:focus {
    box-shadow: 0 0 0 2px rgba(15, 23, 42, 0.08) !important;
}

/* Tabs & Inputs Light Polish */
[data-baseweb="tab-list"] {
    background-color: #FFFFFF !important;
    border-bottom: 1px solid #E2E8F0 !important;
    gap: 1rem !important;
    padding: 0 0.75rem !important;
}
[data-baseweb="tab"] {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: #64748B !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #0F172A !important;
}

/* Ring Alert Row */
.sp-ring-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.55rem 0.78rem;
    background: #FFFFFF;
    border: 1px solid var(--border-hairline);
    border-radius: 6px;
    margin-top: 0.45rem;
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.72rem;
    color: #0F172A;
    box-shadow: var(--shadow-card);
}

/* Divider */
.sp-divider {
    height: 1px;
    background: var(--border-hairline);
    margin: 0.75rem 0;
}
</style>
"""
st.markdown(BANKING_LIGHT_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Bootstrap Persistent Application Objects
# ---------------------------------------------------------------------------
def _ensure_bootstrap() -> None:
    if "sp_sim" not in st.session_state:
        st.session_state["sp_sim"] = IndianPaymentSimulator(seed=2026)
    if "sp_store" not in st.session_state:
        st.session_state["sp_store"] = HybridStateStore()
    if "sp_live_enabled" not in st.session_state:
        st.session_state["sp_live_enabled"] = True
    if "sp_tick_sec" not in st.session_state:
        st.session_state["sp_tick_sec"] = 1.5
    if "sp_noise_rate" not in st.session_state:
        st.session_state["sp_noise_rate"] = 0.08
    if "sp_review_thresh" not in st.session_state:
        st.session_state["sp_review_thresh"] = 40
    if "sp_block_thresh" not in st.session_state:
        st.session_state["sp_block_thresh"] = 70
    if "sp_last_tick" not in st.session_state:
        st.session_state["sp_last_tick"] = 0.0
    if "sp_selected_txn_id" not in st.session_state:
        st.session_state["sp_selected_txn_id"] = None
    if "sp_last_action_msg" not in st.session_state:
        st.session_state["sp_last_action_msg"] = "Stream initialized"

    store: HybridStateStore = st.session_state["sp_store"]
    if not store.get_transactions():
        sim: IndianPaymentSimulator = st.session_state["sp_sim"]
        engine = FraudScoringEngine(
            store=store,
            review_threshold=st.session_state["sp_review_thresh"],
            block_threshold=st.session_state["sp_block_thresh"],
        )
        for raw in sim.seed_initial_history(count=22):
            engine.evaluate_and_ingest(raw)
        st.session_state["sp_last_tick"] = time.time()


_ensure_bootstrap()

sim: IndianPaymentSimulator = st.session_state["sp_sim"]
store: HybridStateStore = st.session_state["sp_store"]


def _get_engine() -> FraudScoringEngine:
    return FraudScoringEngine(
        store=store,
        review_threshold=int(st.session_state["sp_review_thresh"]),
        block_threshold=int(st.session_state["sp_block_thresh"]),
    )


def _render_html(markup: str) -> None:
    """Render HTML via st.markdown with zero leading spaces per line."""
    clean = "\n".join(line.lstrip() for line in markup.splitlines() if line.strip())
    st.markdown(clean, unsafe_allow_html=True)


def _display_decision(decision: str) -> str:
    return "FLAGGED" if decision == "REVIEW" else decision


def _pill_html(decision: str) -> str:
    label = _display_decision(decision)
    cls_map = {
        "APPROVED": "sp-pill-approved",
        "FLAGGED": "sp-pill-flagged",
        "BLOCKED": "sp-pill-blocked",
    }
    cls = cls_map.get(label, "sp-pill-neutral")
    return f'<span class="sp-pill {cls}">{html.escape(label)}</span>'


def _score_color(score: int) -> str:
    if score >= int(st.session_state["sp_block_thresh"]):
        return "#B91C1C"
    if score >= int(st.session_state["sp_review_thresh"]):
        return "#B45309"
    return "#047857"


def _ingest_batch(raw_txns: List[Dict[str, Any]], label: str) -> None:
    engine = _get_engine()
    latest = None
    for raw in raw_txns:
        latest = engine.evaluate_and_ingest(raw)
    if latest is not None:
        st.session_state["sp_selected_txn_id"] = latest["txn_id"]
    st.session_state["sp_last_tick"] = time.time()
    st.session_state["sp_last_action_msg"] = label


# ---------------------------------------------------------------------------
# Sidebar: Risk Policy & Threat Simulation Controls
# ---------------------------------------------------------------------------
with st.sidebar:
    _render_html(
        '<div style="font-size:0.95rem;font-weight:700;color:#0F172A;letter-spacing:-0.01em;">SentinelPay Controls</div>'
        '<div style="font-size:0.74rem;color:#64748B;margin-top:2px;">Risk Policy &amp; Threat Simulation</div>'
    )

    _render_html('<div class="sp-side-section">Stream Engine</div>')
    live_toggle = st.toggle(
        "Live Transaction Stream",
        value=bool(st.session_state["sp_live_enabled"]),
        key="ui_live_toggle",
    )
    st.session_state["sp_live_enabled"] = live_toggle

    tick_sec = st.select_slider(
        "Stream Cadence (sec)",
        options=[1.0, 1.5, 2.5, 4.0],
        value=float(st.session_state["sp_tick_sec"]),
    )
    st.session_state["sp_tick_sec"] = tick_sec

    noise_pct = st.slider(
        "Organic Anomaly Rate (%)",
        min_value=0,
        max_value=25,
        value=int(round(st.session_state["sp_noise_rate"] * 100)),
        step=2,
    )
    st.session_state["sp_noise_rate"] = noise_pct / 100.0

    _render_html('<div class="sp-side-section">Attack Scenario Injectors</div>')
    if st.button("▲ Inject Impossible Travel", width="stretch"):
        recent_cities = store.get_recent_card_cities()
        batch = sim.inject_impossible_travel(recent_card_cities=recent_cities)
        _ingest_batch(batch, "Injected: Impossible Travel attack")

    if st.button("▲ Inject Velocity Burst", width="stretch"):
        batch = sim.inject_velocity_burst()
        _ingest_batch(batch, "Injected: 5-txn velocity burst")

    if st.button("▲ Inject Fraud Ring", width="stretch"):
        batch = sim.inject_fraud_ring()
        _ingest_batch(batch, "Injected: 5-card shared-device fraud ring")

    if st.button("▲ Inject ATO Anomaly", width="stretch"):
        batch = sim.inject_ato_anomaly()
        _ingest_batch(batch, "Injected: Account takeover spend outlier")

    _render_html('<div class="sp-side-section">Risk Policy Thresholds</div>')
    block_th = st.slider("Block Threshold", min_value=55, max_value=90, value=int(st.session_state["sp_block_thresh"]), step=5)
    review_th = st.slider("Flagged Threshold", min_value=20, max_value=block_th - 10, value=min(int(st.session_state["sp_review_thresh"]), block_th - 10), step=5)
    st.session_state["sp_block_thresh"] = block_th
    st.session_state["sp_review_thresh"] = review_th

    _render_html('<div class="sp-side-section">Ledger Filters</div>')
    filter_decision = st.selectbox("Decision Tier", ["ALL", "BLOCKED", "FLAGGED", "APPROVED"], index=0)
    filter_city = st.selectbox("Indian Corridor", ["ALL CITIES"] + list(INDIAN_CITIES.keys()), index=0)
    filter_query = st.text_input("Search Txn / Card / Merchant", value="", placeholder="e.g. Tanishq, 4532, TXN-")


# ---------------------------------------------------------------------------
# Top Utility Control Row (Outside fragment for instant manual triggers)
# ---------------------------------------------------------------------------
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4, ctrl_c5 = st.columns([4.6, 1.15, 1.15, 1.15, 1.15])
with ctrl_c1:
    _render_html(
        f'<div class="mono" style="font-size:0.74rem;color:#64748B;padding-top:0.42rem;">'
        f'Last Event: <span style="color:#0F172A;font-weight:600;">{html.escape(st.session_state["sp_last_action_msg"])}</span>'
        f'</div>'
    )
with ctrl_c2:
    if st.button("Step +1 Txn", width="stretch"):
        _ingest_batch([sim.generate_normal_txn(organic_noise_rate=st.session_state["sp_noise_rate"])], "Step: +1 txn ingested")
with ctrl_c3:
    if st.button("Burst +10", width="stretch"):
        now = time.time()
        batch = [
            sim.generate_normal_txn(now_ts=now - (9 - i) * 0.4, organic_noise_rate=st.session_state["sp_noise_rate"])
            for i in range(10)
        ]
        _ingest_batch(batch, "Burst: +10 txns ingested")
with ctrl_c4:
    pause_label = "■ Pause Stream" if st.session_state["sp_live_enabled"] else "● Resume Stream"
    if st.button(pause_label, width="stretch"):
        st.session_state["sp_live_enabled"] = not st.session_state["sp_live_enabled"]
        st.session_state["sp_last_action_msg"] = "Stream paused" if not st.session_state["sp_live_enabled"] else "Stream resumed"
        st.rerun()
with ctrl_c5:
    if st.button("Reset Window", width="stretch"):
        store.reset()
        st.session_state["sp_selected_txn_id"] = None
        engine = _get_engine()
        for raw in sim.seed_initial_history(count=18):
            engine.evaluate_and_ingest(raw)
        st.session_state["sp_last_tick"] = time.time()
        st.session_state["sp_last_action_msg"] = "Window reset & reseeded"
        st.rerun()


# ---------------------------------------------------------------------------
# Live Risk Console Fragment
# ---------------------------------------------------------------------------
fragment_interval: Optional[float] = float(st.session_state["sp_tick_sec"]) if st.session_state["sp_live_enabled"] else None


@st.fragment(run_every=fragment_interval)
def render_live_soc_console() -> None:
    now = time.time()
    if st.session_state["sp_live_enabled"]:
        elapsed_since_tick = now - float(st.session_state["sp_last_tick"])
        if elapsed_since_tick >= float(st.session_state["sp_tick_sec"]) * 0.85:
            raw = sim.generate_normal_txn(
                now_ts=now,
                organic_noise_rate=float(st.session_state["sp_noise_rate"]),
            )
            _get_engine().evaluate_and_ingest(raw)
            st.session_state["sp_last_tick"] = now

    all_txns = store.get_transactions()
    total_count = len(all_txns)
    blocked_txns = [t for t in all_txns if t["decision"] == "BLOCKED"]
    flagged_txns = [t for t in all_txns if t["decision"] == "REVIEW"]
    approved_txns = [t for t in all_txns if t["decision"] == "APPROVED"]

    total_inr = sum(float(t["amount_inr"]) for t in all_txns)
    blocked_inr = sum(float(t["amount_inr"]) for t in blocked_txns)
    flagged_inr = sum(float(t["amount_inr"]) for t in flagged_txns)
    approved_inr = sum(float(t["amount_inr"]) for t in approved_txns)

    block_rate = (len(blocked_txns) / total_count * 100.0) if total_count else 0.0
    approval_rate = (len(approved_txns) / total_count * 100.0) if total_count else 0.0
    avg_risk = (sum(int(t["risk_score"]) for t in all_txns) / total_count) if total_count else 0.0
    avg_latency = (sum(float(t.get("latency_ms", 0.4)) for t in all_txns) / total_count) if total_count else 0.0
    ring_clusters = detect_ring_clusters(all_txns)

    # Top Navigation Header
    stream_pill = (
        '<span class="sp-sys-pill sp-sys-online">● Live Stream</span>'
        if st.session_state["sp_live_enabled"]
        else '<span class="sp-sys-pill sp-sys-paused">■ Stream Paused</span>'
    )
    latency_display = f"{avg_latency:.2f}ms" if avg_latency > 0 else "<12ms"

    _render_html(
        f"""
        <div class="sp-topbar">
            <div class="sp-brand-row">
                <span class="sp-brand-title">SentinelPay</span>
                <span class="sp-brand-sub">Risk &amp; Fraud Operations</span>
            </div>
            <div class="sp-status-group">
                <span class="sp-sys-pill sp-sys-online">● Engine Operational</span>
                <span class="sp-sys-pill mono">Latency &lt;12ms ({latency_display})</span>
                {stream_pill}
            </div>
        </div>
        """
    )

    # 5-Card KPI Strip
    _render_html(
        f"""
        <div class="sp-kpi-grid">
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">Txn Throughput</div>
                <div class="sp-kpi-value">{total_count}</div>
                <div class="sp-kpi-sub">Vol: {format_inr(total_inr)}</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">Blocked Exposure</div>
                <div class="sp-kpi-value" style="color:#B91C1C;">{format_inr(blocked_inr)}</div>
                <div class="sp-kpi-sub">{len(blocked_txns)} blocked ({block_rate:.1f}%)</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">Flagged Queue</div>
                <div class="sp-kpi-value" style="color:#B45309;">{len(flagged_txns)}</div>
                <div class="sp-kpi-sub">Exposure: {format_inr(flagged_inr)}</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">Approval Rate</div>
                <div class="sp-kpi-value" style="color:#047857;">{approval_rate:.1f}%</div>
                <div class="sp-kpi-sub">Cleared: {format_inr(approved_inr)}</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">Mean Risk / Rings</div>
                <div class="sp-kpi-value">{avg_risk:.1f}<span style="font-size:0.82rem;color:#64748B;"> / 100</span></div>
                <div class="sp-kpi-sub">Active rings: {len(ring_clusters)} | {latency_display}</div>
            </div>
        </div>
        """
    )

    # Apply Ledger Filters
    filtered_txns = all_txns
    if filter_decision != "ALL":
        target_decision = "REVIEW" if filter_decision == "FLAGGED" else filter_decision
        filtered_txns = [t for t in filtered_txns if t["decision"] == target_decision]
    if filter_city != "ALL CITIES":
        filtered_txns = [t for t in filtered_txns if t["city"] == filter_city]
    if filter_query.strip():
        q = filter_query.strip().lower()
        filtered_txns = [
            t
            for t in filtered_txns
            if q in str(t["txn_id"]).lower()
            or q in str(t["card_masked"]).lower()
            or q in str(t["merchant"]).lower()
            or q in str(t["device_id"]).lower()
            or q in str(t["ip_hash"]).lower()
        ]

    if filtered_txns:
        valid_ids = [t["txn_id"] for t in filtered_txns]
        if st.session_state["sp_selected_txn_id"] not in valid_ids:
            flagged_first = next((t["txn_id"] for t in filtered_txns if t["decision"] != "APPROVED"), valid_ids[0])
            st.session_state["sp_selected_txn_id"] = flagged_first
    elif all_txns:
        st.session_state["sp_selected_txn_id"] = all_txns[0]["txn_id"]

    # -----------------------------------------------------------------------
    # Row 1: Live Authorization Ledger (Left) + Telemetry & Rule Inspector (Right)
    # -----------------------------------------------------------------------
    col_ledger, col_inspector = st.columns([1.6, 1.0], gap="medium")

    with col_ledger:
        sel_bar_1, sel_bar_2 = st.columns([3.0, 1.3])
        with sel_bar_1:
            if filtered_txns:
                option_labels = {
                    t["txn_id"]: f"{t['txn_id']}  |  {_display_decision(t['decision'])} ({t['risk_score']})  |  {t['merchant']}  |  {t['amount_formatted']}"
                    for t in filtered_txns[:60]
                }
                opt_ids = list(option_labels.keys())
                current_idx = opt_ids.index(st.session_state["sp_selected_txn_id"]) if st.session_state["sp_selected_txn_id"] in opt_ids else 0
                chosen_id = st.selectbox(
                    "Inspect Transaction",
                    options=opt_ids,
                    index=current_idx,
                    format_func=lambda tid: option_labels[tid],
                    label_visibility="collapsed",
                )
                st.session_state["sp_selected_txn_id"] = chosen_id
        with sel_bar_2:
            if st.button("Jump to Latest Alert", width="stretch"):
                alert_txn = next((t for t in all_txns if t["decision"] in ("BLOCKED", "REVIEW")), None)
                if alert_txn:
                    st.session_state["sp_selected_txn_id"] = alert_txn["txn_id"]

        _render_html(
            f'<div class="sp-panel-header">'
            f'<span class="sp-panel-title">Live Authorization Ledger</span>'
            f'<span class="sp-panel-meta">Showing {min(len(filtered_txns), 60)} of {len(filtered_txns)} matched ({total_count} in window)</span>'
            f'</div>'
        )

        rows_html: List[str] = []
        selected_id = st.session_state["sp_selected_txn_id"]
        for txn in filtered_txns[:60]:
            is_sel = txn["txn_id"] == selected_id
            row_cls = "sp-row-selected" if is_sel else ""
            r_score = int(txn["risk_score"])
            r_col = _score_color(r_score)
            marker = "▸ " if is_sel else ""
            rows_html.append(
                f'<tr class="{row_cls}">'
                f'<td class="mono" style="color:#64748B;">{html.escape(str(txn["ts_ist"])[:12])}</td>'
                f'<td class="mono" style="color:#0F172A;font-weight:600;">{marker}{html.escape(str(txn["txn_id"]))}</td>'
                f'<td class="mono" style="color:#334155;">{html.escape(str(txn["card_masked"]))}</td>'
                f'<td style="color:#0F172A;font-weight:500;">{html.escape(str(txn["merchant"]))}</td>'
                f'<td style="color:#475569;">{html.escape(str(txn["city"]))}</td>'
                f'<td class="mono" style="color:#0F172A;text-align:right;font-weight:600;">{html.escape(str(txn["amount_formatted"]))}</td>'
                f'<td class="mono" style="color:{r_col};text-align:right;font-weight:700;">{r_score:02d}</td>'
                f'<td>{_pill_html(str(txn["decision"]))}</td>'
                f'<td class="mono" style="color:#64748B;font-size:0.70rem;">{html.escape(str(txn["primary_signal"]))}</td>'
                f'</tr>'
            )

        if not rows_html:
            rows_html.append(
                '<tr><td colspan="9" class="mono" style="text-align:center;color:#64748B;padding:2rem;">'
                'NO TRANSACTIONS MATCH CURRENT FILTER CRITERIA</td></tr>'
            )

        table_html = (
            '<div class="sp-table-wrap">'
            '<table class="sp-table">'
            '<thead><tr>'
            '<th>Time (IST)</th>'
            '<th>Txn ID</th>'
            '<th>Card BIN</th>'
            '<th>Merchant</th>'
            '<th>City</th>'
            '<th style="text-align:right;">Amount</th>'
            '<th style="text-align:right;">Risk</th>'
            '<th>Decision</th>'
            '<th>Primary Signal</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows_html)}</tbody>'
            '</table></div>'
        )
        _render_html(table_html)

    with col_inspector:
        selected_txn = next((t for t in all_txns if t["txn_id"] == st.session_state["sp_selected_txn_id"]), None)
        _render_html(
            '<div class="sp-panel-header">'
            '<span class="sp-panel-title">Telemetry &amp; Rule Inspector</span>'
            '<span class="sp-panel-meta">Weighted Vector Breakdown</span>'
            '</div>'
        )

        if selected_txn is None:
            _render_html('<div class="sp-card mono" style="color:#64748B;">No transaction selected</div>')
        else:
            tel = selected_txn["telemetry"]
            scores = selected_txn["scores"]
            weights = selected_txn["weights"]
            analyst_badge = (
                f'<span class="sp-pill sp-pill-neutral">Analyst: {html.escape(str(selected_txn["analyst_status"]))}</span>'
                if selected_txn.get("analyst_status", "AUTO") != "AUTO"
                else ""
            )

            geo_summary = (
                f"{tel['prev_city']} → {selected_txn['city']} ({tel['distance_km']:,.0f} km | {tel['implied_speed_kmh']:,.0f} km/h)"
                if tel.get("prev_city")
                else "First txn in window"
            )

            factor_specs = [
                ("VELOCITY (25%)", int(scores["velocity"]), weights["velocity"]),
                ("GEO HAVERSINE (30%)", int(scores["geo_haversine"]), weights["geo_haversine"]),
                ("AMT ANOMALY (25%)", int(scores["anomaly"]), weights["anomaly"]),
                ("FRAUD RING (20%)", int(scores["fraud_ring"]), weights["fraud_ring"]),
            ]

            bars_html = []
            for label, val, _w in factor_specs:
                col = _score_color(val)
                bars_html.append(
                    f'<div class="sp-factor-row">'
                    f'<div class="sp-factor-head"><span>{label}</span><span style="color:{col};font-weight:700;">{val:02d} / 100</span></div>'
                    f'<div class="sp-bar-track"><div class="sp-bar-fill" style="width:{max(2, val)}%;background:{col};"></div></div>'
                    f'</div>'
                )

            reason_pills = " ".join(
                f'<span class="sp-pill sp-pill-neutral" style="margin-right:4px;margin-bottom:4px;">{html.escape(code)}</span>'
                for code in selected_txn["reason_codes"]
            )
            audit_lines = "".join(
                f'<div style="font-size:0.75rem;color:#334155;margin-bottom:4px;">&#9656; {html.escape(line)}</div>'
                for line in selected_txn["explanation"]
            )

            inspector_html = f"""
            <div class="sp-card">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem;">
                    <div>
                        <div class="mono" style="font-size:0.95rem;font-weight:700;color:#0F172A;">{html.escape(str(selected_txn["txn_id"]))}</div>
                        <div class="mono" style="font-size:0.70rem;color:#64748B;">{html.escape(str(selected_txn["ts_ist"]))} &bull; {selected_txn.get("latency_ms", 0.4):.2f} ms</div>
                    </div>
                    <div style="display:flex;gap:0.35rem;align-items:center;flex-wrap:wrap;justify-content:flex-end;">
                        {analyst_badge}
                        {_pill_html(str(selected_txn["decision"]))}
                        <span class="mono" style="font-size:1.05rem;font-weight:700;color:{_score_color(int(selected_txn['risk_score']))};">{int(selected_txn['risk_score']):02d}</span>
                    </div>
                </div>

                <div class="sp-kv-grid">
                    <div>
                        <div class="sp-kv-label">Card / Network</div>
                        <div class="sp-kv-val">{html.escape(str(selected_txn["card_masked"]))}</div>
                        <div style="font-size:0.69rem;color:#64748B;">{html.escape(str(selected_txn["card_network"]))}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Amount / Baseline</div>
                        <div class="sp-kv-val" style="font-weight:700;">{html.escape(str(selected_txn["amount_formatted"]))}</div>
                        <div class="mono" style="font-size:0.69rem;color:#64748B;">Mean {format_inr(float(selected_txn['card_baseline_mean']))} ({tel['amount_ratio']}x)</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Merchant / Channel</div>
                        <div class="sp-kv-val">{html.escape(str(selected_txn["merchant"]))}</div>
                        <div class="mono" style="font-size:0.69rem;color:#64748B;">{html.escape(str(selected_txn["mcc"]))} &bull; {html.escape(str(selected_txn["channel"]))}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Location / Coords</div>
                        <div class="sp-kv-val">{html.escape(str(selected_txn["city"]))}</div>
                        <div class="mono" style="font-size:0.69rem;color:#64748B;">{selected_txn['lat']:.4f}, {selected_txn['lon']:.4f}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Device &amp; IP Entity</div>
                        <div class="mono" style="font-size:0.72rem;color:#0F172A;">{html.escape(str(selected_txn["device_id"]))} &bull; {html.escape(str(selected_txn["ip_hash"]))}</div>
                        <div class="mono" style="font-size:0.69rem;color:#64748B;">Linked cards: DEV={tel['device_linked_cards']} | IP={tel['ip_linked_cards']}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Haversine / Velocity</div>
                        <div class="mono" style="font-size:0.71rem;color:#0F172A;">{html.escape(geo_summary)}</div>
                        <div class="mono" style="font-size:0.69rem;color:#64748B;">60s={tel['txns_60s']} txns | 5m={tel['txns_5m']} txns</div>
                    </div>
                </div>

                {"".join(bars_html)}
                <div class="sp-divider"></div>
                <div style="margin-bottom:0.45rem;">{reason_pills}</div>
                {audit_lines}
            </div>
            """
            _render_html(inspector_html)

            act1, act2, act3 = st.columns(3)
            with act1:
                if st.button("Approve Override", key="btn_override_approve", width="stretch"):
                    store.update_analyst_status(selected_txn["txn_id"], "APPROVED_OVERRIDE")
                    st.session_state["sp_last_action_msg"] = f"Analyst approved override: {selected_txn['txn_id']}"
                    st.rerun()
            with act2:
                if st.button("Confirm Block", key="btn_confirm_block", width="stretch"):
                    store.update_analyst_status(selected_txn["txn_id"], "CONFIRMED_BLOCK")
                    st.session_state["sp_last_action_msg"] = f"Analyst confirmed block: {selected_txn['txn_id']}"
                    st.rerun()
            with act3:
                if st.button("Escalate Case", key="btn_escalate", width="stretch"):
                    store.update_analyst_status(selected_txn["txn_id"], "ESCALATED")
                    st.session_state["sp_last_action_msg"] = f"Case escalated to L2 SOC: {selected_txn['txn_id']}"
                    st.rerun()

    _render_html('<div style="height:0.85rem;"></div>')

    # -----------------------------------------------------------------------
    # Row 2: Visual Intelligence Split (Timeline & Cities | Topology Graph)
    # -----------------------------------------------------------------------
    col_left_viz, col_right_graph = st.columns([1.0, 1.0], gap="medium")

    with col_left_viz:
        _render_html(
            '<div class="sp-panel-header">'
            '<span class="sp-panel-title">Risk Telemetry &amp; Indian Corridor Exposure</span>'
            '<span class="sp-panel-meta">Live Sliding Window</span>'
            '</div>'
        )
        tab_timeline, tab_cities = st.tabs(["Risk Timeline", "Corridor Exposure Matrix"])

        with tab_timeline:
            if all_txns:
                chrono = list(reversed(all_txns[:100]))
                fig_tl = go.Figure()
                for tier, label, color in (
                    ("APPROVED", "Approved", "#047857"),
                    ("REVIEW", "Flagged", "#D97706"),
                    ("BLOCKED", "Blocked", "#DC2626"),
                ):
                    subset = [t for t in chrono if t["decision"] == tier]
                    if not subset:
                        continue
                    fig_tl.add_trace(
                        go.Scatter(
                            x=[t["ts_ist"][:8] for t in subset],
                            y=[int(t["risk_score"]) for t in subset],
                            mode="markers",
                            name=label,
                            marker=dict(
                                color=color,
                                size=[min(18, max(7, 5 + (float(t["amount_inr"]) ** 0.22))) for t in subset],
                                opacity=0.88,
                                line=dict(color="#FFFFFF", width=1.2),
                            ),
                            hovertext=[
                                f"<b>{t['txn_id']}</b><br>{t['merchant']} ({t['city']})<br>"
                                f"Amount: {t['amount_formatted']} | Risk: {t['risk_score']}<br>"
                                f"Signal: {t['primary_signal']}"
                                for t in subset
                            ],
                            hoverinfo="text",
                            hoverlabel=dict(
                                bgcolor="#0F172A",
                                bordercolor="#0F172A",
                                font=dict(family="JetBrains Mono, monospace", size=11, color="#FFFFFF"),
                            ),
                        )
                    )

                fig_tl.add_hline(
                    y=int(st.session_state["sp_block_thresh"]),
                    line_dash="dot",
                    line_color="#DC2626",
                    line_width=1.2,
                )
                fig_tl.add_hline(
                    y=int(st.session_state["sp_review_thresh"]),
                    line_dash="dot",
                    line_color="#D97706",
                    line_width=1.2,
                )
                fig_tl.update_layout(
                    paper_bgcolor="#FFFFFF",
                    plot_bgcolor="#FFFFFF",
                    height=355,
                    margin=dict(l=42, r=12, t=28, b=36),
                    yaxis=dict(
                        title="Risk Score",
                        range=[-4, 105],
                        gridcolor="#F1F5F9",
                        zeroline=False,
                        showline=True,
                        linecolor="#E2E8F0",
                        tickfont=dict(family="JetBrains Mono, monospace", size=10, color="#64748B"),
                        title_font=dict(family="Inter, sans-serif", size=11, color="#475569"),
                    ),
                    xaxis=dict(
                        gridcolor="#F8FAFC",
                        showline=True,
                        linecolor="#E2E8F0",
                        tickfont=dict(family="JetBrains Mono, monospace", size=9, color="#64748B"),
                        nticks=8,
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.01,
                        xanchor="left",
                        x=0.0,
                        font=dict(family="Inter, sans-serif", size=11, color="#475569"),
                        bgcolor="rgba(255,255,255,0)",
                    ),
                )
                st.plotly_chart(fig_tl, width="stretch", config={"displayModeBar": False})

        with tab_cities:
            city_rows = []
            for city_name in INDIAN_CITIES:
                c_txns = [t for t in all_txns if t["city"] == city_name]
                c_blocked = [t for t in c_txns if t["decision"] == "BLOCKED"]
                c_flagged = [t for t in c_txns if t["decision"] == "REVIEW"]
                city_rows.append(
                    {
                        "City": city_name,
                        "Txns": len(c_txns),
                        "Blocked": len(c_blocked),
                        "Flagged": len(c_flagged),
                        "Volume": format_inr(sum(float(t["amount_inr"]) for t in c_txns)),
                        "Blocked INR": format_inr(sum(float(t["amount_inr"]) for t in c_blocked)),
                        "Max Risk": max((int(t["risk_score"]) for t in c_txns), default=0),
                    }
                )
            df_cities = pd.DataFrame(city_rows)
            st.dataframe(
                df_cities,
                width="stretch",
                hide_index=True,
                height=340,
            )

    with col_right_graph:
        g_head_1, g_head_2 = st.columns([1.8, 1.4])
        with g_head_1:
            _render_html(
                '<div style="font-size:0.78rem;font-weight:600;color:#0F172A;'
                'letter-spacing:0.03em;text-transform:uppercase;padding-top:0.45rem;">Entity-Relationship Topology</div>'
            )
        with g_head_2:
            graph_focus = st.selectbox(
                "Graph Focus",
                ["Flagged & Ring Clusters", "Selected Txn Neighbourhood", "Active Window (Latest 60)"],
                index=0,
                label_visibility="collapsed",
            )

        fig_graph, g_metrics = build_entity_graph(
            all_txns,
            focus_mode=graph_focus,
            selected_txn_id=st.session_state["sp_selected_txn_id"],
        )
        _render_html(
            f'<div class="sp-panel-header">'
            f'<span class="sp-panel-title">Card &harr; Device &harr; IP &harr; Merchant</span>'
            f'<span class="sp-panel-meta">Nodes: {g_metrics["nodes"]} | Edges: {g_metrics["edges"]} | Clusters: {g_metrics["components"]}</span>'
            f'</div>'
        )
        st.plotly_chart(fig_graph, width="stretch", config={"displayModeBar": False})

        if ring_clusters:
            ring_items = []
            for cl in ring_clusters[:3]:
                ring_items.append(
                    f'<div class="sp-ring-item">'
                    f'<span><span class="sp-pill sp-pill-blocked">{html.escape(cl["entity_type"])}</span> '
                    f'<span style="color:#0F172A;font-weight:600;">{html.escape(cl["entity_id"])}</span> '
                    f'<span style="color:#64748B;">({cl["linked_cards"]} cards | {", ".join(cl["cities"][:3])})</span></span>'
                    f'<span style="color:#B91C1C;font-weight:700;">{html.escape(cl["exposure_formatted"])}</span>'
                    f'</div>'
                )
            _render_html("".join(ring_items))
        else:
            _render_html(
                '<div class="sp-ring-item" style="color:#64748B;">'
                '<span>● No multi-card shared device or IP rings detected in active window</span>'
                '<span class="sp-pill sp-pill-approved">CLEAN</span>'
                '</div>'
            )


render_live_soc_console()
