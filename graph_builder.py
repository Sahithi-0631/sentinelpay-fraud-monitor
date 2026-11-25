"""
SentinelPay Entity-Relationship Topology Graph Builder.

Constructs a light-canvas NetworkX + Plotly graph linking Cards, Devices,
IP Hashes, and Merchants to expose multi-card fraud rings and shared
compromised infrastructure.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import plotly.graph_objects as go

from simulator import format_inr


ENTITY_COLORS = {
    "CARD": "#2563EB",      # Royal blue
    "DEVICE": "#7C3AED",    # Deep violet
    "MERCHANT": "#D97706",  # Warm amber
    "IP": "#475569",        # Institutional slate
}


def detect_ring_clusters(txns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identify shared Device or IP infrastructure linked to >= 2 distinct cards
    in the active transaction window.
    """
    dev_map: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"cards": set(), "txns": 0, "exposure": 0.0, "max_risk": 0, "cities": set()}
    )
    ip_map: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"cards": set(), "txns": 0, "exposure": 0.0, "max_risk": 0, "cities": set()}
    )

    for txn in txns:
        card = str(txn["card_masked"])
        amt = float(txn["amount_inr"])
        risk = int(txn["risk_score"])
        city = str(txn["city"])

        for bucket, key in ((dev_map, str(txn["device_id"])), (ip_map, str(txn["ip_hash"]))):
            bucket[key]["cards"].add(card)
            bucket[key]["txns"] += 1
            bucket[key]["exposure"] += amt
            bucket[key]["max_risk"] = max(bucket[key]["max_risk"], risk)
            bucket[key]["cities"].add(city)

    clusters: List[Dict[str, Any]] = []
    for entity_type, source in (("DEVICE", dev_map), ("IP_HASH", ip_map)):
        for entity_id, stats in source.items():
            if len(stats["cards"]) >= 2:
                clusters.append(
                    {
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "linked_cards": len(stats["cards"]),
                        "txn_count": stats["txns"],
                        "exposure_inr": stats["exposure"],
                        "exposure_formatted": format_inr(stats["exposure"]),
                        "max_risk": stats["max_risk"],
                        "cities": sorted(stats["cities"]),
                    }
                )

    clusters.sort(key=lambda c: (c["linked_cards"], c["max_risk"], c["exposure_inr"]), reverse=True)
    return clusters


def _select_subgraph_txns(
    txns: List[Dict[str, Any]],
    focus_mode: str,
    selected_txn_id: Optional[str],
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Filter active transactions for crisp, readable graph topology."""
    if not txns:
        return [], set()

    focus_nodes: Set[str] = set()

    if focus_mode == "Selected Txn Neighbourhood" and selected_txn_id:
        target = next((t for t in txns if t["txn_id"] == selected_txn_id), None)
        if target:
            seed_entities = {
                f"CARD:{target['card_id']}",
                f"DEV:{target['device_id']}",
                f"IP:{target['ip_hash']}",
            }
            focus_nodes = set(seed_entities)
            matched = [
                t
                for t in txns
                if f"CARD:{t['card_id']}" in seed_entities
                or f"DEV:{t['device_id']}" in seed_entities
                or f"IP:{t['ip_hash']}" in seed_entities
            ]
            return matched[:60], focus_nodes

    if focus_mode == "Flagged & Ring Clusters":
        ring_entities = {c["entity_id"] for c in detect_ring_clusters(txns)}
        flagged_cards = {
            t["card_id"]
            for t in txns
            if int(t["risk_score"]) >= 40
            or t["device_id"] in ring_entities
            or t["ip_hash"] in ring_entities
        }
        filtered = [
            t
            for t in txns
            if t["card_id"] in flagged_cards
            or t["device_id"] in ring_entities
            or t["ip_hash"] in ring_entities
            or int(t["risk_score"]) >= 40
        ]
        if filtered:
            return filtered[:70], focus_nodes
        return txns[:20], focus_nodes

    return txns[:55], focus_nodes


def build_entity_graph(
    txns: List[Dict[str, Any]],
    focus_mode: str = "Flagged & Ring Clusters",
    selected_txn_id: Optional[str] = None,
) -> Tuple[go.Figure, Dict[str, int]]:
    """
    Build a light-canvas Plotly figure visualizing Card <-> Device <-> IP <-> Merchant topology.
    Returns (plotly.graph_objects.Figure, graph_metrics_dict).
    """
    subset, focus_nodes = _select_subgraph_txns(txns, focus_mode, selected_txn_id)

    graph = nx.Graph()
    node_meta: Dict[str, Dict[str, Any]] = {}
    edge_meta: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def ensure_node(nid: str, ntype: str, label: str, extra: str) -> None:
        if nid not in node_meta:
            graph.add_node(nid)
            node_meta[nid] = {
                "type": ntype,
                "label": label,
                "extra": extra,
                "max_risk": 0,
                "txns": 0,
                "exposure": 0.0,
            }

    for txn in subset:
        risk = int(txn["risk_score"])
        amt = float(txn["amount_inr"])
        c_node = f"CARD:{txn['card_id']}"
        d_node = f"DEV:{txn['device_id']}"
        i_node = f"IP:{txn['ip_hash']}"
        m_node = f"MERCH:{txn['merchant']}"

        ensure_node(
            c_node,
            "CARD",
            f"{str(txn['card_masked'])[:4]}..{str(txn['card_masked'])[-4:]}",
            f"{txn['card_network']} | Home: {txn['home_city']}",
        )
        ensure_node(d_node, "DEVICE", str(txn["device_id"]), "Device Fingerprint")
        ensure_node(i_node, "IP", str(txn["ip_hash"]), "Network IP Hash")
        ensure_node(m_node, "MERCHANT", str(txn["merchant"]), f"MCC: {txn['mcc']}")

        for nid in (c_node, d_node, i_node, m_node):
            node_meta[nid]["max_risk"] = max(node_meta[nid]["max_risk"], risk)
            node_meta[nid]["txns"] += 1
            node_meta[nid]["exposure"] += amt

        for u, v in ((c_node, d_node), (d_node, i_node), (c_node, m_node)):
            key = tuple(sorted((u, v)))
            if key not in edge_meta:
                graph.add_edge(u, v)
                edge_meta[key] = {"max_risk": risk, "count": 1}
            else:
                edge_meta[key]["max_risk"] = max(edge_meta[key]["max_risk"], risk)
                edge_meta[key]["count"] += 1

    fig = go.Figure()

    if graph.number_of_nodes() == 0:
        fig.update_layout(
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            height=360,
            margin=dict(l=12, r=12, t=12, b=12),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, showline=True, mirror=True, linecolor="#E2E8F0", linewidth=1),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, showline=True, mirror=True, linecolor="#E2E8F0", linewidth=1),
            annotations=[
                dict(
                    text="NO ACTIVE ENTITIES IN CURRENT FILTER",
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    font=dict(family="JetBrains Mono, monospace", size=12, color="#64748B"),
                )
            ],
        )
        return fig, {"nodes": 0, "edges": 0, "components": 0}

    pos = nx.spring_layout(graph, k=0.65, iterations=55, seed=42)

    normal_x, normal_y = [], []
    high_risk_x, high_risk_y = [], []

    for u, v in graph.edges():
        key = tuple(sorted((u, v)))
        edge_risk = edge_meta[key]["max_risk"]
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        if edge_risk >= 70 or (graph.degree(u) >= 3 and edge_risk >= 40) or (graph.degree(v) >= 3 and edge_risk >= 40):
            high_risk_x.extend([x0, x1, None])
            high_risk_y.extend([y0, y1, None])
        else:
            normal_x.extend([x0, x1, None])
            normal_y.extend([y0, y1, None])

    for name, ex, ey, color, width in (
        ("Normal Link", normal_x, normal_y, "#CBD5E1", 1.5),
        ("High-Risk / Fraud-Ring Link", high_risk_x, high_risk_y, "#DC2626", 2.5),
    ):
        if ex:
            fig.add_trace(
                go.Scatter(
                    x=ex,
                    y=ey,
                    mode="lines",
                    line=dict(width=width, color=color),
                    hoverinfo="none",
                    name=name,
                    showlegend=False,
                )
            )

    symbol_map = {
        "CARD": ("circle", "Card"),
        "DEVICE": ("diamond", "Device"),
        "MERCHANT": ("triangle-up", "Merchant"),
        "IP": ("square", "IP Hash"),
    }

    for ntype, (symbol, display_name) in symbol_map.items():
        nodes = [n for n, meta in node_meta.items() if meta["type"] == ntype]
        if not nodes:
            continue

        xs, ys, colors, sizes, line_colors, line_widths, texts, hovers = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )

        base_color = ENTITY_COLORS[ntype]
        for nid in nodes:
            meta = node_meta[nid]
            x, y = pos[nid]
            xs.append(x)
            ys.append(y)
            colors.append(base_color)

            deg = graph.degree(nid)
            sizes.append(min(22, 11 + deg * 2.0))

            risk = meta["max_risk"]
            if nid in focus_nodes:
                line_colors.append("#0F172A")
                line_widths.append(2.5)
            elif risk >= 70:
                line_colors.append("#DC2626")
                line_widths.append(2.2)
            else:
                line_colors.append("#FFFFFF")
                line_widths.append(1.5)

            short_lbl = meta["label"] if deg >= 2 or risk >= 70 or nid in focus_nodes else ""
            texts.append(short_lbl)
            hovers.append(
                f"<b>{display_name}: {meta['label']}</b><br>"
                f"{meta['extra']}<br>"
                f"Linked Edges: {deg} | Txns: {meta['txns']}<br>"
                f"Max Risk: {risk} | Exposure: {format_inr(meta['exposure'])}"
            )

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers+text",
                name=display_name,
                text=texts,
                textposition="top center",
                textfont=dict(family="JetBrains Mono, monospace", size=9, color="#0F172A"),
                hovertext=hovers,
                hoverinfo="text",
                hoverlabel=dict(
                    bgcolor="#0F172A",
                    bordercolor="#0F172A",
                    font=dict(family="JetBrains Mono, monospace", size=11, color="#FFFFFF"),
                ),
                marker=dict(
                    symbol=symbol,
                    size=sizes,
                    color=colors,
                    line=dict(color=line_colors, width=line_widths),
                ),
            )
        )

    fig.update_layout(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        height=360,
        margin=dict(l=8, r=8, t=28, b=8),
        hovermode="closest",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0.0,
            font=dict(family="Inter, sans-serif", size=11, color="#475569"),
            bgcolor="rgba(255,255,255,0)",
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            showline=True,
            mirror=True,
            linecolor="#E2E8F0",
            linewidth=1,
            fixedrange=False,
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            showline=True,
            mirror=True,
            linecolor="#E2E8F0",
            linewidth=1,
            fixedrange=False,
        ),
    )

    metrics = {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": nx.number_connected_components(graph),
    }
    return fig, metrics
