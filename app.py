"""
SentinelPay — Real-Time Transaction Fraud Monitor.

Single-service institutional SOC console built with Streamlit, NetworkX,
Plotly, and a hybrid Upstash Redis / in-memory sliding-window state layer.
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
    page_title="SentinelPay — Real-Time Transaction Fraud Monitor",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Institutional Dark-Slate Design System (No emojis, hairline borders, mono)
# ---------------------------------------------------------------------------
INSTITUTIONAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
    --bg-canvas: #0B0F17;
    --bg-panel: #111827;
    --bg-panel-alt: #0F1522;
    --border-hairline: #1F2937;
    --text-primary: #F3F4F6;
    --text-muted: #9CA3AF;
    --text-dim: #6B7280;
    --accent-blue: #3B82F6;
    --status-green: #10B981;
    --status-amber: #F59E0B;
    --status-red: #EF4444;
}

/* Hide default Streamlit chrome & top colored bar */
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
    display: none !important;
}
[data-testid="stHeader"] {
    background: rgba(11, 15, 23, 0.0) !important;
    height: 2.25rem !important;
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background-color: var(--bg-canvas);
    color: var(--text-primary);
}

.main .block-container {
    padding-top: 0.9rem !important;
    padding-bottom: 1.2rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
    max-width: 100% !important;
}

section[data-testid="stSidebar"] {
    background-color: #0E131D !important;
    border-right: 1px solid var(--border-hairline) !important;
}
section[data-testid="stSidebar"] .block-container {
    padding: 1rem 0.9rem !important;
}

.mono {
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace !important;
    font-variant-numeric: tabular-nums;
}

/* Top Utility Header */
.sp-topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    background: var(--bg-panel);
    border: 1px solid var(--border-hairline);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.85rem;
}
.sp-brand-title {
    font-size: 0.95rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace;
}
.sp-brand-sub {
    font-size: 0.72rem;
    color: var(--text-muted);
    letter-spacing: 0.04em;
    margin-top: 2px;
}
.sp-status-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.55rem;
}
.sp-sys-pill {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.28rem 0.6rem;
    border-radius: 4px;
    border: 1px solid var(--border-hairline);
    background: #0B0F17;
    color: var(--text-muted);
    letter-spacing: 0.03em;
}
.sp-sys-online {
    color: var(--status-green);
    background: rgba(16, 185, 129, 0.10);
    border-color: rgba(16, 185, 129, 0.25);
}
.sp-sys-paused {
    color: var(--status-amber);
    background: rgba(245, 158, 11, 0.10);
    border-color: rgba(245, 158, 11, 0.25);
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
    background: var(--bg-panel);
    border: 1px solid var(--border-hairline);
    border-radius: 6px;
    padding: 0.85rem 1rem;
}
.sp-kpi-label {
    font-size: 0.70rem;
    font-weight: 600;
    letter-spacing: 0.07em;
    color: var(--text-muted);
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}
.sp-kpi-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.32rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
}
.sp-kpi-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-dim);
    margin-top: 0.35rem;
}

/* Panel Headers */
.sp-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.65rem 0.9rem;
    background: var(--bg-panel);
    border: 1px solid var(--border-hairline);
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
.sp-panel-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--text-primary);
    text-transform: uppercase;
}
.sp-panel-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.70rem;
    color: var(--text-muted);
}

/* Status Pills */
.sp-pill {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    padding: 0.16rem 0.48rem;
    border-radius: 4px;
    white-space: nowrap;
}
.sp-pill-approved {
    color: #10B981;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.25);
}
.sp-pill-review {
    color: #F59E0B;
    background: rgba(245, 158, 11, 0.12);
    border: 1px solid rgba(245, 158, 11, 0.25);
}
.sp-pill-blocked {
    color: #EF4444;
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid rgba(239, 68, 68, 0.25);
}
.sp-pill-blue {
    color: #60A5FA;
    background: rgba(59, 130, 246, 0.12);
    border: 1px solid rgba(59, 130, 246, 0.28);
}

/* Live Ledger Table */
.sp-table-wrap {
    background: var(--bg-panel);
    border: 1px solid var(--border-hairline);
    border-bottom-left-radius: 6px;
    border-bottom-right-radius: 6px;
    max-height: 410px;
    overflow-y: auto;
    overflow-x: auto;
}
.sp-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.76rem;
}
.sp-table thead th {
    position: sticky;
    top: 0;
    background: #0F1522;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-align: left;
    padding: 0.55rem 0.7rem;
    border-bottom: 1px solid var(--border-hairline);
    z-index: 2;
    white-space: nowrap;
}
.sp-table tbody tr {
    border-bottom: 1px solid #182030;
    transition: background-color 0.12s ease;
}
.sp-table tbody tr:hover {
    background-color: #161F30;
}
.sp-table tbody tr.sp-row-selected {
    background-color: rgba(59, 130, 246, 0.11);
}
.sp-table tbody td {
    padding: 0.48rem 0.7rem;
    vertical-align: middle;
    white-space: nowrap;
}

/* Inspector Card */
.sp-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-hairline);
    border-radius: 6px;
    padding: 1rem;
}
.sp-kv-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.55rem 0.9rem;
    padding: 0.7rem 0;
    border-top: 1px solid var(--border-hairline);
    border-bottom: 1px solid var(--border-hairline);
    margin: 0.65rem 0;
}
.sp-kv-label {
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--text-dim);
    text-transform: uppercase;
}
.sp-kv-val {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--text-primary);
    margin-top: 1px;
}

/* Risk Factor Bar */
.sp-factor-row {
    margin-bottom: 0.52rem;
}
.sp-factor-head {
    display: flex;
    justify-content: space-between;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.71rem;
    color: var(--text-muted);
    margin-bottom: 3px;
}
.sp-bar-track {
    width: 100%;
    height: 6px;
    background: #0B0F17;
    border: 1px solid var(--border-hairline);
    border-radius: 3px;
    overflow: hidden;
}
.sp-bar-fill {
    height: 100%;
    border-radius: 2px;
}

/* Sidebar Headings & Buttons */
.sp-side-section {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.70rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    text-transform: uppercase;
    margin: 0.8rem 0 0.4rem 0;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid var(--border-hairline);
}
div.stButton > button {
    background-color: #111827;
    color: #F3F4F6;
    border: 1px solid #2A3441;
    border-radius: 5px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.74rem;
    font-weight: 500;
    padding: 0.42rem 0.75rem;
    transition: border-color 0.15s ease, background-color 0.15s ease;
}
div.stButton > button:hover {
    border-color: #3B82F6;
    background-color: #162033;
    color: #FFFFFF;
}
div.stButton > button[kind="primary"] {
    background-color: rgba(59, 130, 246, 0.16);
    border-color: #3B82F6;
    color: #93C5FD;
}

/* Ring Alert Row */
.sp-ring-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.48rem 0.7rem;
    background: #0E1420;
    border: 1px solid var(--border-hairline);
    border-radius: 4px;
    margin-bottom: 0.4rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
}

/* Divider */
.sp-divider {
    height: 1px;
    background: var(--border-hairline);
    margin: 0.75rem 0;
}
</style>
"""
st.markdown(INSTITUTIONAL_CSS, unsafe_allow_html=True)


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
        st.session_state["sp_last_action_msg"] = "STREAM INITIALIZED"

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


def _pill_html(decision: str) -> str:
    cls_map = {
        "APPROVED": "sp-pill-approved",
        "REVIEW": "sp-pill-review",
        "BLOCKED": "sp-pill-blocked",
    }
    cls = cls_map.get(decision, "sp-pill-blue")
    return f'<span class="sp-pill {cls}">{html.escape(decision)}</span>'


def _score_color(score: int) -> str:
    if score >= int(st.session_state["sp_block_thresh"]):
        return "#EF4444"
    if score >= int(st.session_state["sp_review_thresh"]):
        return "#F59E0B"
    return "#10B981"


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
# Sidebar: SOC Operations & Attack Scenario Injectors
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="mono" style="font-size:0.86rem;font-weight:700;color:#F3F4F6;'
        'letter-spacing:0.06em;">SENTINELPAY // CONTROLS</div>'
        '<div style="font-size:0.70rem;color:#9CA3AF;margin-top:2px;">'
        'Risk Policy &amp; Threat Simulation</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sp-side-section">Stream Engine</div>', unsafe_allow_html=True)
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

    st.markdown('<div class="sp-side-section">Attack Scenario Injectors</div>', unsafe_allow_html=True)
    if st.button("▲ INJECT IMPOSSIBLE TRAVEL", width="stretch"):
        recent_cities = store.get_recent_card_cities()
        batch = sim.inject_impossible_travel(recent_card_cities=recent_cities)
        _ingest_batch(batch, "INJECTED: IMPOSSIBLE TRAVEL ATTACK")

    if st.button("▲ INJECT VELOCITY BURST", width="stretch"):
        batch = sim.inject_velocity_burst()
        _ingest_batch(batch, "INJECTED: 5-TXN CARD-TESTING VELOCITY BURST")

    if st.button("▲ INJECT FRAUD RING", width="stretch"):
        batch = sim.inject_fraud_ring()
        _ingest_batch(batch, "INJECTED: 5-CARD SHARED-DEVICE FRAUD RING")

    if st.button("▲ INJECT ATO ANOMALY", width="stretch"):
        batch = sim.inject_ato_anomaly()
        _ingest_batch(batch, "INJECTED: ACCOUNT TAKEOVER SPEND OUTLIER")

    st.markdown('<div class="sp-side-section">Risk Policy Thresholds</div>', unsafe_allow_html=True)
    block_th = st.slider("Block Threshold", min_value=55, max_value=90, value=int(st.session_state["sp_block_thresh"]), step=5)
    review_th = st.slider("Review Threshold", min_value=20, max_value=block_th - 10, value=min(int(st.session_state["sp_review_thresh"]), block_th - 10), step=5)
    st.session_state["sp_block_thresh"] = block_th
    st.session_state["sp_review_thresh"] = review_th

    st.markdown('<div class="sp-side-section">Ledger Filters</div>', unsafe_allow_html=True)
    filter_decision = st.selectbox("Decision Tier", ["ALL", "BLOCKED", "REVIEW", "APPROVED"], index=0)
    filter_city = st.selectbox("Indian Corridor", ["ALL CITIES"] + list(INDIAN_CITIES.keys()), index=0)
    filter_query = st.text_input("Search Txn / Card / Merchant", value="", placeholder="e.g. Tanishq, 4532, TXN-")


# ---------------------------------------------------------------------------
# Top Utility Control Row (Outside fragment for instant manual triggers)
# ---------------------------------------------------------------------------
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4, ctrl_c5 = st.columns([4.6, 1.15, 1.15, 1.15, 1.15])
with ctrl_c1:
    st.markdown(
        f'<div class="mono" style="font-size:0.72rem;color:#9CA3AF;padding-top:0.35rem;">'
        f'LAST EVENT: <span style="color:#E5E7EB;">{html.escape(st.session_state["sp_last_action_msg"])}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
with ctrl_c2:
    if st.button("STEP +1 TXN", width="stretch"):
        _ingest_batch([sim.generate_normal_txn(organic_noise_rate=st.session_state["sp_noise_rate"])], "STEP: +1 TXN INGESTED")
with ctrl_c3:
    if st.button("BURST +10", width="stretch"):
        now = time.time()
        batch = [
            sim.generate_normal_txn(now_ts=now - (9 - i) * 0.4, organic_noise_rate=st.session_state["sp_noise_rate"])
            for i in range(10)
        ]
        _ingest_batch(batch, "BURST: +10 TXNS INGESTED")
with ctrl_c4:
    pause_label = "■ PAUSE STREAM" if st.session_state["sp_live_enabled"] else "● RESUME STREAM"
    if st.button(pause_label, width="stretch"):
        st.session_state["sp_live_enabled"] = not st.session_state["sp_live_enabled"]
        st.session_state["sp_last_action_msg"] = "STREAM PAUSED" if not st.session_state["sp_live_enabled"] else "STREAM RESUMED"
        st.rerun()
with ctrl_c5:
    if st.button("RESET WINDOW", width="stretch"):
        store.reset()
        st.session_state["sp_selected_txn_id"] = None
        engine = _get_engine()
        for raw in sim.seed_initial_history(count=18):
            engine.evaluate_and_ingest(raw)
        st.session_state["sp_last_tick"] = time.time()
        st.session_state["sp_last_action_msg"] = "WINDOW RESET & RESEEDED"
        st.rerun()


# ---------------------------------------------------------------------------
# Live SOC Fragment (Refreshes seamlessly when Live Stream is enabled)
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
    review_txns = [t for t in all_txns if t["decision"] == "REVIEW"]
    approved_txns = [t for t in all_txns if t["decision"] == "APPROVED"]

    total_inr = sum(float(t["amount_inr"]) for t in all_txns)
    blocked_inr = sum(float(t["amount_inr"]) for t in blocked_txns)
    review_inr = sum(float(t["amount_inr"]) for t in review_txns)
    approved_inr = sum(float(t["amount_inr"]) for t in approved_txns)

    block_rate = (len(blocked_txns) / total_count * 100.0) if total_count else 0.0
    approval_rate = (len(approved_txns) / total_count * 100.0) if total_count else 0.0
    avg_risk = (sum(int(t["risk_score"]) for t in all_txns) / total_count) if total_count else 0.0
    avg_latency = (sum(float(t.get("latency_ms", 0.4)) for t in all_txns) / total_count) if total_count else 0.0
    ring_clusters = detect_ring_clusters(all_txns)

    # Top Institutional Utility Header Bar
    stream_pill = (
        '<span class="sp-sys-pill sp-sys-online">● STREAM LIVE</span>'
        if st.session_state["sp_live_enabled"]
        else '<span class="sp-sys-pill sp-sys-paused">■ STREAM PAUSED</span>'
    )
    latency_display = f"{avg_latency:.2f}ms" if avg_latency > 0 else "<12ms"

    _render_html(
        f"""
        <div class="sp-topbar">
            <div>
                <div class="sp-brand-title">SENTINELPAY // REAL-TIME FRAUD OPERATIONS</div>
                <div class="sp-brand-sub">INDIAN PAYMENTS RISK CONSOLE &mdash; VELOCITY, HAVERSINE GEO, ANOMALY &amp; ENTITY TOPOLOGY</div>
            </div>
            <div class="sp-status-group">
                <span class="sp-sys-pill sp-sys-online">● ENGINE ONLINE | LATENCY: &lt;12ms ({latency_display})</span>
                <span class="sp-sys-pill">MODE: REAL-TIME STREAM</span>
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
                <div class="sp-kpi-label">TXN THROUGHPUT</div>
                <div class="sp-kpi-value">{total_count}</div>
                <div class="sp-kpi-sub">VOL: {format_inr(total_inr)}</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">BLOCKED EXPOSURE</div>
                <div class="sp-kpi-value" style="color:#EF4444;">{format_inr(blocked_inr)}</div>
                <div class="sp-kpi-sub">{len(blocked_txns)} BLOCKED ({block_rate:.1f}%)</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">REVIEW QUEUE</div>
                <div class="sp-kpi-value" style="color:#F59E0B;">{len(review_txns)}</div>
                <div class="sp-kpi-sub">EXPOSURE: {format_inr(review_inr)}</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">APPROVAL RATE</div>
                <div class="sp-kpi-value" style="color:#10B981;">{approval_rate:.1f}%</div>
                <div class="sp-kpi-sub">CLEARED: {format_inr(approved_inr)}</div>
            </div>
            <div class="sp-kpi-card">
                <div class="sp-kpi-label">MEAN RISK / RINGS</div>
                <div class="sp-kpi-value">{avg_risk:.1f}<span style="font-size:0.82rem;color:#6B7280;"> / 100</span></div>
                <div class="sp-kpi-sub">ACTIVE RINGS: {len(ring_clusters)} | {latency_display}</div>
            </div>
        </div>
        """
    )

    # Apply Ledger Filters
    filtered_txns = all_txns
    if filter_decision != "ALL":
        filtered_txns = [t for t in filtered_txns if t["decision"] == filter_decision]
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

    # Resolve selected transaction for Inspector
    if filtered_txns:
        valid_ids = [t["txn_id"] for t in filtered_txns]
        if st.session_state["sp_selected_txn_id"] not in valid_ids:
            flagged_first = next((t["txn_id"] for t in filtered_txns if t["decision"] != "APPROVED"), valid_ids[0])
            st.session_state["sp_selected_txn_id"] = flagged_first
    elif all_txns:
        st.session_state["sp_selected_txn_id"] = all_txns[0]["txn_id"]

    # -----------------------------------------------------------------------
    # Row 1: Live Transaction Ledger (Left 62%) + Telemetry Inspector (Right 38%)
    # -----------------------------------------------------------------------
    col_ledger, col_inspector = st.columns([1.6, 1.0], gap="medium")

    with col_ledger:
        sel_bar_1, sel_bar_2 = st.columns([3.0, 1.3])
        with sel_bar_1:
            if filtered_txns:
                option_labels = {
                    t["txn_id"]: f"{t['txn_id']}  |  {t['decision']} ({t['risk_score']})  |  {t['merchant']}  |  {t['amount_formatted']}"
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
            if st.button("JUMP TO LATEST ALERT", width="stretch"):
                alert_txn = next((t for t in all_txns if t["decision"] in ("BLOCKED", "REVIEW")), None)
                if alert_txn:
                    st.session_state["sp_selected_txn_id"] = alert_txn["txn_id"]

        st.markdown(
            f'<div class="sp-panel-header">'
            f'<span class="sp-panel-title">LIVE TRANSACTION LEDGER</span>'
            f'<span class="sp-panel-meta">SHOWING {min(len(filtered_txns), 60)} OF {len(filtered_txns)} MATCHED ({total_count} IN WINDOW)</span>'
            f'</div>',
            unsafe_allow_html=True,
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
                f'<td class="mono" style="color:#9CA3AF;">{html.escape(str(txn["ts_ist"])[:12])}</td>'
                f'<td class="mono" style="color:#F3F4F6;font-weight:600;">{marker}{html.escape(str(txn["txn_id"]))}</td>'
                f'<td class="mono" style="color:#D1D5DB;">{html.escape(str(txn["card_masked"]))}</td>'
                f'<td style="color:#E5E7EB;">{html.escape(str(txn["merchant"]))}</td>'
                f'<td style="color:#9CA3AF;">{html.escape(str(txn["city"]))}</td>'
                f'<td class="mono" style="color:#F3F4F6;text-align:right;font-weight:600;">{html.escape(str(txn["amount_formatted"]))}</td>'
                f'<td class="mono" style="color:{r_col};text-align:right;font-weight:700;">{r_score:02d}</td>'
                f'<td>{_pill_html(str(txn["decision"]))}</td>'
                f'<td class="mono" style="color:#9CA3AF;font-size:0.70rem;">{html.escape(str(txn["primary_signal"]))}</td>'
                f'</tr>'
            )

        if not rows_html:
            rows_html.append(
                '<tr><td colspan="9" class="mono" style="text-align:center;color:#6B7280;padding:2rem;">'
                'NO TRANSACTIONS MATCH CURRENT FILTER CRITERIA</td></tr>'
            )

        table_html = (
            '<div class="sp-table-wrap">'
            '<table class="sp-table">'
            '<thead><tr>'
            '<th>TIME (IST)</th>'
            '<th>TXN ID</th>'
            '<th>CARD BIN</th>'
            '<th>MERCHANT</th>'
            '<th>CITY</th>'
            '<th style="text-align:right;">AMOUNT</th>'
            '<th style="text-align:right;">RISK</th>'
            '<th>DECISION</th>'
            '<th>PRIMARY SIGNAL</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows_html)}</tbody>'
            '</table></div>'
        )
        st.markdown(table_html, unsafe_allow_html=True)

    with col_inspector:
        selected_txn = next((t for t in all_txns if t["txn_id"] == st.session_state["sp_selected_txn_id"]), None)
        st.markdown(
            '<div class="sp-panel-header">'
            '<span class="sp-panel-title">TELEMETRY &amp; RULE INSPECTOR</span>'
            '<span class="sp-panel-meta">WEIGHTED VECTOR BREAKDOWN</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        if selected_txn is None:
            st.markdown('<div class="sp-card mono" style="color:#6B7280;">NO TRANSACTION SELECTED</div>', unsafe_allow_html=True)
        else:
            tel = selected_txn["telemetry"]
            scores = selected_txn["scores"]
            weights = selected_txn["weights"]
            analyst_badge = (
                f'<span class="sp-pill sp-pill-blue">ANALYST: {html.escape(str(selected_txn["analyst_status"]))}</span>'
                if selected_txn.get("analyst_status", "AUTO") != "AUTO"
                else ""
            )

            geo_summary = (
                f"{tel['prev_city']} → {selected_txn['city']} ({tel['distance_km']:,.0f} km | {tel['implied_speed_kmh']:,.0f} km/h)"
                if tel.get("prev_city")
                else "FIRST TXN IN WINDOW"
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
                f'<span class="sp-pill sp-pill-blue" style="margin-right:4px;margin-bottom:4px;">{html.escape(code)}</span>'
                for code in selected_txn["reason_codes"]
            )
            audit_lines = "".join(
                f'<div style="font-size:0.74rem;color:#D1D5DB;margin-bottom:3px;">&#9656; {html.escape(line)}</div>'
                for line in selected_txn["explanation"]
            )

            inspector_html = f"""
            <div class="sp-card" style="border-top-left-radius:0;border-top-right-radius:0;">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem;">
                    <div>
                        <div class="mono" style="font-size:0.94rem;font-weight:700;color:#F3F4F6;">{html.escape(str(selected_txn["txn_id"]))}</div>
                        <div class="mono" style="font-size:0.70rem;color:#9CA3AF;">{html.escape(str(selected_txn["ts_ist"]))} &bull; {selected_txn.get("latency_ms", 0.4):.2f} ms</div>
                    </div>
                    <div style="display:flex;gap:0.35rem;align-items:center;">
                        {analyst_badge}
                        {_pill_html(str(selected_txn["decision"]))}
                        <span class="mono" style="font-size:1.05rem;font-weight:700;color:{_score_color(int(selected_txn['risk_score']))};">{int(selected_txn['risk_score']):02d}</span>
                    </div>
                </div>

                <div class="sp-kv-grid">
                    <div>
                        <div class="sp-kv-label">Card / Network</div>
                        <div class="sp-kv-val">{html.escape(str(selected_txn["card_masked"]))}</div>
                        <div style="font-size:0.68rem;color:#6B7280;">{html.escape(str(selected_txn["card_network"]))}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Amount / Baseline</div>
                        <div class="sp-kv-val" style="font-weight:700;">{html.escape(str(selected_txn["amount_formatted"]))}</div>
                        <div class="mono" style="font-size:0.68rem;color:#6B7280;">MEAN {format_inr(float(selected_txn['card_baseline_mean']))} ({tel['amount_ratio']}x)</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Merchant / Channel</div>
                        <div class="sp-kv-val">{html.escape(str(selected_txn["merchant"]))}</div>
                        <div class="mono" style="font-size:0.68rem;color:#6B7280;">{html.escape(str(selected_txn["mcc"]))} &bull; {html.escape(str(selected_txn["channel"]))}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Location / Coords</div>
                        <div class="sp-kv-val">{html.escape(str(selected_txn["city"]))}</div>
                        <div class="mono" style="font-size:0.68rem;color:#6B7280;">{selected_txn['lat']:.4f}, {selected_txn['lon']:.4f}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Device &amp; IP Entity</div>
                        <div class="mono" style="font-size:0.72rem;color:#E5E7EB;">{html.escape(str(selected_txn["device_id"]))} &bull; {html.escape(str(selected_txn["ip_hash"]))}</div>
                        <div class="mono" style="font-size:0.68rem;color:#6B7280;">LINKED CARDS: DEV={tel['device_linked_cards']} | IP={tel['ip_linked_cards']}</div>
                    </div>
                    <div>
                        <div class="sp-kv-label">Haversine / Velocity</div>
                        <div class="mono" style="font-size:0.71rem;color:#E5E7EB;">{html.escape(geo_summary)}</div>
                        <div class="mono" style="font-size:0.68rem;color:#6B7280;">60S={tel['txns_60s']} TXNS | 5M={tel['txns_5m']} TXNS</div>
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
                if st.button("APPROVE OVERRIDE", key="btn_override_approve", width="stretch"):
                    store.update_analyst_status(selected_txn["txn_id"], "APPROVED_OVERRIDE")
                    st.session_state["sp_last_action_msg"] = f"ANALYST APPROVED OVERRIDE: {selected_txn['txn_id']}"
                    st.rerun()
            with act2:
                if st.button("CONFIRM BLOCK", key="btn_confirm_block", width="stretch"):
                    store.update_analyst_status(selected_txn["txn_id"], "CONFIRMED_BLOCK")
                    st.session_state["sp_last_action_msg"] = f"ANALYST CONFIRMED BLOCK: {selected_txn['txn_id']}"
                    st.rerun()
            with act3:
                if st.button("ESCALATE CASE", key="btn_escalate", width="stretch"):
                    store.update_analyst_status(selected_txn["txn_id"], "ESCALATED")
                    st.session_state["sp_last_action_msg"] = f"CASE ESCALATED TO L2 SOC: {selected_txn['txn_id']}"
                    st.rerun()

    st.markdown('<div style="height:0.85rem;"></div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Row 2: Visual Intelligence Split (Timeline & Cities | Topology Graph)
    # -----------------------------------------------------------------------
    col_left_viz, col_right_graph = st.columns([1.0, 1.0], gap="medium")

    with col_left_viz:
        st.markdown(
            '<div class="sp-panel-header">'
            '<span class="sp-panel-title">RISK TELEMETRY &amp; INDIAN CORRIDOR EXPOSURE</span>'
            '<span class="sp-panel-meta">LIVE SLIDING WINDOW</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        tab_timeline, tab_cities = st.tabs(["RISK TIMELINE", "CORRIDOR EXPOSURE MATRIX"])

        with tab_timeline:
            if all_txns:
                chrono = list(reversed(all_txns[:100]))
                fig_tl = go.Figure()
                for tier, color in (("APPROVED", "#10B981"), ("REVIEW", "#F59E0B"), ("BLOCKED", "#EF4444")):
                    subset = [t for t in chrono if t["decision"] == tier]
                    if not subset:
                        continue
                    fig_tl.add_trace(
                        go.Scatter(
                            x=[t["ts_ist"][:8] for t in subset],
                            y=[int(t["risk_score"]) for t in subset],
                            mode="markers",
                            name=tier,
                            marker=dict(
                                color=color,
                                size=[min(18, max(7, 5 + (float(t["amount_inr"]) ** 0.22))) for t in subset],
                                opacity=0.88,
                                line=dict(color="#0B0F17", width=1),
                            ),
                            hovertext=[
                                f"<b>{t['txn_id']}</b><br>{t['merchant']} ({t['city']})<br>"
                                f"Amount: {t['amount_formatted']} | Risk: {t['risk_score']}<br>"
                                f"Signal: {t['primary_signal']}"
                                for t in subset
                            ],
                            hoverinfo="text",
                        )
                    )

                fig_tl.add_hline(
                    y=int(st.session_state["sp_block_thresh"]),
                    line_dash="dot",
                    line_color="#EF4444",
                    line_width=1.2,
                )
                fig_tl.add_hline(
                    y=int(st.session_state["sp_review_thresh"]),
                    line_dash="dot",
                    line_color="#F59E0B",
                    line_width=1.2,
                )
                fig_tl.update_layout(
                    paper_bgcolor="#111827",
                    plot_bgcolor="#0B0F17",
                    height=355,
                    margin=dict(l=38, r=12, t=12, b=36),
                    yaxis=dict(
                        title="Risk Score",
                        range=[-4, 105],
                        gridcolor="#1F2937",
                        zeroline=False,
                        tickfont=dict(family="JetBrains Mono, monospace", size=10, color="#9CA3AF"),
                        title_font=dict(family="JetBrains Mono, monospace", size=10, color="#9CA3AF"),
                    ),
                    xaxis=dict(
                        gridcolor="#161D2B",
                        tickfont=dict(family="JetBrains Mono, monospace", size=9, color="#9CA3AF"),
                        nticks=8,
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.01,
                        xanchor="left",
                        x=0.0,
                        font=dict(family="JetBrains Mono, monospace", size=10, color="#9CA3AF"),
                        bgcolor="rgba(0,0,0,0)",
                    ),
                )
                st.plotly_chart(fig_tl, width="stretch", config={"displayModeBar": False})

        with tab_cities:
            city_rows = []
            for city_name in INDIAN_CITIES:
                c_txns = [t for t in all_txns if t["city"] == city_name]
                c_blocked = [t for t in c_txns if t["decision"] == "BLOCKED"]
                c_review = [t for t in c_txns if t["decision"] == "REVIEW"]
                city_rows.append(
                    {
                        "CITY": city_name,
                        "TXNS": len(c_txns),
                        "BLOCKED": len(c_blocked),
                        "REVIEW": len(c_review),
                        "VOLUME": format_inr(sum(float(t["amount_inr"]) for t in c_txns)),
                        "BLOCKED INR": format_inr(sum(float(t["amount_inr"]) for t in c_blocked)),
                        "MAX RISK": max((int(t["risk_score"]) for t in c_txns), default=0),
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
            st.markdown(
                '<div class="mono" style="font-size:0.76rem;font-weight:600;color:#F3F4F6;'
                'letter-spacing:0.06em;padding-top:0.4rem;">ENTITY-RELATIONSHIP TOPOLOGY</div>',
                unsafe_allow_html=True,
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
        st.markdown(
            f'<div class="sp-panel-header">'
            f'<span class="sp-panel-title">CARD &harr; DEVICE &harr; IP &harr; MERCHANT</span>'
            f'<span class="sp-panel-meta">NODES: {g_metrics["nodes"]} | EDGES: {g_metrics["edges"]} | CLUSTERS: {g_metrics["components"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig_graph, width="stretch", config={"displayModeBar": False})

        if ring_clusters:
            ring_items = []
            for cl in ring_clusters[:3]:
                ring_items.append(
                    f'<div class="sp-ring-item">'
                    f'<span><span class="sp-pill sp-pill-blocked">{html.escape(cl["entity_type"])}</span> '
                    f'<span style="color:#F3F4F6;font-weight:600;">{html.escape(cl["entity_id"])}</span> '
                    f'<span style="color:#9CA3AF;">({cl["linked_cards"]} CARDS | {", ".join(cl["cities"][:3])})</span></span>'
                    f'<span style="color:#EF4444;font-weight:700;">{html.escape(cl["exposure_formatted"])}</span>'
                    f'</div>'
                )
            st.markdown("".join(ring_items), unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="sp-ring-item" style="color:#6B7280;">'
                '<span>● NO MULTI-CARD SHARED DEVICE OR IP RINGS DETECTED IN ACTIVE WINDOW</span>'
                '<span>CLEAN</span>'
                '</div>',
                unsafe_allow_html=True,
            )


render_live_soc_console()
