"""
SentinelPay Weighted Risk-Scoring Engine & Resilient Hybrid State Layer.

Provides:
- HybridStateStore: Upstash Redis (via UPSTASH_REDIS_URL in st.secrets, env, or .env)
  with seamless, automatic fallback to st.session_state in-memory sliding windows.
- FraudScoringEngine: Sub-12ms weighted scoring across Velocity, Haversine
  Impossible Travel, Spend/Behavioral Anomaly, and Entity-Link Fraud Rings.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

try:
    import redis
except ImportError:  # pragma: no cover - handled by requirements.txt
    redis = None  # type: ignore[assignment]


EARTH_RADIUS_KM = 6371.0

DEFAULT_WEIGHTS: Dict[str, float] = {
    "velocity": 0.25,
    "geo_haversine": 0.30,
    "anomaly": 0.25,
    "fraud_ring": 0.20,
}

HIGH_RISK_MCCS = {"Jewellery", "Electronics", "Airlines", "Luxury Retail"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in kilometers between two WGS84 coordinates."""
    phi1, lam1, phi2, lam2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dphi = phi2 - phi1
    dlam = lam2 - lam1
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _read_dotenv_var(key: str) -> Optional[str]:
    """Read a key from a local .env file without requiring python-dotenv."""
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
        except OSError:
            continue
    return None


def resolve_redis_url() -> Optional[str]:
    """Resolve UPSTASH_REDIS_URL from environment, .env, or st.secrets safely."""
    env_url = os.environ.get("UPSTASH_REDIS_URL")
    if env_url and env_url.strip():
        return env_url.strip()

    dotenv_url = _read_dotenv_var("UPSTASH_REDIS_URL")
    if dotenv_url and dotenv_url.strip():
        return dotenv_url.strip()

    try:
        if "UPSTASH_REDIS_URL" in st.secrets:
            secret_url = str(st.secrets["UPSTASH_REDIS_URL"]).strip()
            if secret_url:
                return secret_url
    except Exception:
        pass
    return None


class HybridStateStore:
    """
    Sliding-window state store supporting Upstash Redis with automatic
    fallback to st.session_state in-memory storage.
    """

    MAX_FEED_TXNS = 300
    MAX_CARD_WINDOW = 30
    WINDOW_TTL_SEC = 3600  # 1-hour active risk window

    def __init__(self) -> None:
        self._init_memory_state()
        self._redis_client: Any = None
        self.backend_label: str = "IN-MEMORY"
        self.redis_status_detail: str = "Session memory active"
        self._connect_redis()

    def _init_memory_state(self) -> None:
        if "sp_txns" not in st.session_state:
            st.session_state["sp_txns"] = []
        if "sp_card_hist" not in st.session_state:
            st.session_state["sp_card_hist"] = {}
        if "sp_dev_cards" not in st.session_state:
            st.session_state["sp_dev_cards"] = {}
        if "sp_ip_cards" not in st.session_state:
            st.session_state["sp_ip_cards"] = {}
        if "sp_flagged_entities" not in st.session_state:
            st.session_state["sp_flagged_entities"] = set()

    def _connect_redis(self) -> None:
        url = resolve_redis_url()
        if not url or redis is None:
            return
        try:
            client = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
            )
            client.ping()
            self._redis_client = client
            self.backend_label = "UPSTASH REDIS"
            self.redis_status_detail = "Connected via UPSTASH_REDIS_URL"
        except Exception as exc:
            self._redis_client = None
            self.backend_label = "IN-MEMORY (FALLBACK)"
            self.redis_status_detail = f"Redis unavailable ({type(exc).__name__})"

    def _fallback_to_memory(self, exc: Exception) -> None:
        self._redis_client = None
        self.backend_label = "IN-MEMORY (FALLBACK)"
        self.redis_status_detail = f"Switched to memory ({type(exc).__name__})"

    def get_entity_context(
        self, card_id: str, device_id: str, ip_hash: str, now_ts: float
    ) -> Dict[str, Any]:
        """Fetch card sliding-window history and linked entity sets in one pass."""
        cutoff = now_ts - self.WINDOW_TTL_SEC

        if self._redis_client is not None:
            try:
                pipe = self._redis_client.pipeline()
                pipe.lrange(f"sp:card:{card_id}", 0, self.MAX_CARD_WINDOW - 1)
                pipe.smembers(f"sp:dev:{device_id}")
                pipe.smembers(f"sp:ip:{ip_hash}")
                pipe.sismember("sp:flagged", device_id)
                pipe.sismember("sp:flagged", ip_hash)
                raw_card, dev_cards, ip_cards, dev_flagged, ip_flagged = pipe.execute()

                card_history = []
                for item in raw_card:
                    parsed = json.loads(item)
                    if float(parsed["timestamp"]) >= cutoff:
                        card_history.append(parsed)
                card_history.sort(key=lambda x: float(x["timestamp"]))
                return {
                    "card_history": card_history,
                    "dev_cards": set(dev_cards or []),
                    "ip_cards": set(ip_cards or []),
                    "entity_flagged": bool(dev_flagged or ip_flagged),
                }
            except Exception as exc:
                self._fallback_to_memory(exc)

        raw_hist: List[Dict[str, Any]] = st.session_state["sp_card_hist"].get(card_id, [])
        card_history = [t for t in raw_hist if float(t["timestamp"]) >= cutoff]
        card_history.sort(key=lambda x: float(x["timestamp"]))
        dev_cards = set(st.session_state["sp_dev_cards"].get(device_id, set()))
        ip_cards = set(st.session_state["sp_ip_cards"].get(ip_hash, set()))
        flagged = st.session_state["sp_flagged_entities"]
        return {
            "card_history": card_history,
            "dev_cards": dev_cards,
            "ip_cards": ip_cards,
            "entity_flagged": (device_id in flagged) or (ip_hash in flagged),
        }

    def record_transaction(self, scored_txn: Dict[str, Any]) -> None:
        """Persist scored transaction into sliding windows and global feed."""
        card_id = str(scored_txn["card_id"])
        device_id = str(scored_txn["device_id"])
        ip_hash = str(scored_txn["ip_hash"])
        compact_card_entry = {
            "txn_id": scored_txn["txn_id"],
            "timestamp": scored_txn["timestamp"],
            "amount_inr": scored_txn["amount_inr"],
            "city": scored_txn["city"],
            "lat": scored_txn["lat"],
            "lon": scored_txn["lon"],
            "device_id": device_id,
            "ip_hash": ip_hash,
            "decision": scored_txn["decision"],
        }

        # Always keep in-memory session mirror updated for fast UI rendering
        self._init_memory_state()
        txns: List[Dict[str, Any]] = st.session_state["sp_txns"]
        txns.insert(0, scored_txn)
        if len(txns) > self.MAX_FEED_TXNS:
            del txns[self.MAX_FEED_TXNS :]

        card_hist = st.session_state["sp_card_hist"].setdefault(card_id, [])
        card_hist.append(compact_card_entry)
        if len(card_hist) > self.MAX_CARD_WINDOW:
            del card_hist[: len(card_hist) - self.MAX_CARD_WINDOW]

        st.session_state["sp_dev_cards"].setdefault(device_id, set()).add(card_id)
        st.session_state["sp_ip_cards"].setdefault(ip_hash, set()).add(card_id)
        if scored_txn["decision"] == "BLOCKED":
            st.session_state["sp_flagged_entities"].add(device_id)
            st.session_state["sp_flagged_entities"].add(ip_hash)

        if self._redis_client is not None:
            try:
                pipe = self._redis_client.pipeline()
                pipe.lpush("sp:txns", json.dumps(scored_txn))
                pipe.ltrim("sp:txns", 0, self.MAX_FEED_TXNS - 1)
                pipe.lpush(f"sp:card:{card_id}", json.dumps(compact_card_entry))
                pipe.ltrim(f"sp:card:{card_id}", 0, self.MAX_CARD_WINDOW - 1)
                pipe.expire(f"sp:card:{card_id}", self.WINDOW_TTL_SEC)
                pipe.sadd(f"sp:dev:{device_id}", card_id)
                pipe.expire(f"sp:dev:{device_id}", self.WINDOW_TTL_SEC)
                pipe.sadd(f"sp:ip:{ip_hash}", card_id)
                pipe.expire(f"sp:ip:{ip_hash}", self.WINDOW_TTL_SEC)
                if scored_txn["decision"] == "BLOCKED":
                    pipe.sadd("sp:flagged", device_id, ip_hash)
                    pipe.expire("sp:flagged", self.WINDOW_TTL_SEC)
                pipe.execute()
            except Exception as exc:
                self._fallback_to_memory(exc)

    def get_transactions(self) -> List[Dict[str, Any]]:
        """Retrieve transactions newest-first."""
        self._init_memory_state()
        if st.session_state["sp_txns"]:
            return st.session_state["sp_txns"]

        if self._redis_client is not None:
            try:
                raw_list = self._redis_client.lrange("sp:txns", 0, self.MAX_FEED_TXNS - 1)
                parsed = [json.loads(item) for item in raw_list]
                st.session_state["sp_txns"] = parsed
                return parsed
            except Exception as exc:
                self._fallback_to_memory(exc)

        return st.session_state["sp_txns"]

    def get_recent_card_cities(self) -> Dict[str, Tuple[str, float]]:
        """Return latest city and timestamp per card from active window."""
        out: Dict[str, Tuple[str, float]] = {}
        for txn in reversed(self.get_transactions()):
            out[str(txn["card_id"])] = (str(txn["city"]), float(txn["timestamp"]))
        return out

    def update_analyst_status(self, txn_id: str, analyst_status: str) -> bool:
        """Update analyst disposition on a transaction."""
        txns = self.get_transactions()
        updated = False
        for idx, txn in enumerate(txns):
            if txn.get("txn_id") == txn_id:
                txn["analyst_status"] = analyst_status
                if analyst_status == "APPROVED_OVERRIDE":
                    txn["decision"] = "APPROVED"
                elif analyst_status == "CONFIRMED_BLOCK":
                    txn["decision"] = "BLOCKED"
                updated = True
                if self._redis_client is not None:
                    try:
                        self._redis_client.lset("sp:txns", idx, json.dumps(txn))
                    except Exception as exc:
                        self._fallback_to_memory(exc)
                break
        return updated

    def reset(self) -> None:
        """Clear all sliding-window and feed state."""
        st.session_state["sp_txns"] = []
        st.session_state["sp_card_hist"] = {}
        st.session_state["sp_dev_cards"] = {}
        st.session_state["sp_ip_cards"] = {}
        st.session_state["sp_flagged_entities"] = set()

        if self._redis_client is not None:
            try:
                keys = list(self._redis_client.scan_iter(match="sp:*", count=200))
                if keys:
                    self._redis_client.delete(*keys)
            except Exception as exc:
                self._fallback_to_memory(exc)


class FraudScoringEngine:
    """
    Deterministic multi-factor risk scoring engine.

    Combines:
      1. Velocity (burst frequency & micro-probing)
      2. Geo-Haversine (impossible physical transit speed)
      3. Behavioral / Amount Anomaly (z-score, MCC shift, new device/city)
      4. Fraud Ring Topology (shared devices/IPs across multiple distinct cards)
    """

    def __init__(
        self,
        store: HybridStateStore,
        review_threshold: int = 40,
        block_threshold: int = 70,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self.store = store
        self.review_threshold = review_threshold
        self.block_threshold = block_threshold
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def evaluate_and_ingest(self, raw_txn: Dict[str, Any]) -> Dict[str, Any]:
        """Score a raw transaction against sliding-window state and persist it."""
        now_ts = float(raw_txn["timestamp"])
        card_id = str(raw_txn["card_id"])
        device_id = str(raw_txn["device_id"])
        ip_hash = str(raw_txn["ip_hash"])

        ctx = self.store.get_entity_context(card_id, device_id, ip_hash, now_ts)

        t_start = time.perf_counter()
        card_hist: List[Dict[str, Any]] = ctx["card_history"]
        dev_cards: set[str] = set(ctx["dev_cards"]) | {card_id}
        ip_cards: set[str] = set(ctx["ip_cards"]) | {card_id}
        entity_flagged: bool = bool(ctx["entity_flagged"])

        reason_codes: List[str] = []
        explanations: List[str] = []

        # ------------------------------------------------------------------
        # 1. Velocity Risk (0 - 100)
        # ------------------------------------------------------------------
        txns_60s = sum(1 for h in card_hist if (now_ts - float(h["timestamp"])) <= 60.0)
        txns_5m = sum(1 for h in card_hist if (now_ts - float(h["timestamp"])) <= 300.0)
        spend_5m = sum(
            float(h["amount_inr"]) for h in card_hist if (now_ts - float(h["timestamp"])) <= 300.0
        ) + float(raw_txn["amount_inr"])
        micro_probes_5m = sum(
            1
            for h in card_hist
            if (now_ts - float(h["timestamp"])) <= 300.0 and float(h["amount_inr"]) <= 550.0
        )

        vel_score = 0.0
        if txns_60s >= 4:
            vel_score = 98.0
            reason_codes.append("VEL_BURST_60S")
            explanations.append(f"Extreme burst: {txns_60s + 1} txns on card within 60s.")
        elif txns_60s >= 2:
            vel_score = 72.0
            reason_codes.append("VEL_ELEVATED_60S")
            explanations.append(f"Elevated cadence: {txns_60s + 1} txns within 60s.")
        elif txns_5m >= 4:
            vel_score = 84.0
            reason_codes.append("VEL_BURST_5M")
            explanations.append(f"Rapid window cadence: {txns_5m + 1} txns within 5m.")
        elif txns_5m >= 2:
            vel_score = 45.0

        if micro_probes_5m >= 3 and float(raw_txn["amount_inr"]) >= 25000.0:
            vel_score = max(vel_score, 95.0)
            reason_codes.append("CARD_TEST_CASHOUT")
            explanations.append(
                f"Card-testing pattern: {micro_probes_5m} micro-probes followed by high-value attempt."
            )

        # ------------------------------------------------------------------
        # 2. Haversine Impossible Travel Risk (0 - 100)
        # ------------------------------------------------------------------
        geo_score = 0.0
        prev_city: Optional[str] = None
        dist_km = 0.0
        elapsed_sec = 0.0
        implied_speed_kmh = 0.0

        if card_hist:
            last_txn = card_hist[-1]
            prev_city = str(last_txn["city"])
            dist_km = haversine_km(
                float(last_txn["lat"]),
                float(last_txn["lon"]),
                float(raw_txn["lat"]),
                float(raw_txn["lon"]),
            )
            elapsed_sec = max(1.0, now_ts - float(last_txn["timestamp"]))
            implied_speed_kmh = dist_km / (elapsed_sec / 3600.0)

            if dist_km >= 180.0 and implied_speed_kmh >= 900.0:
                geo_score = 100.0
                reason_codes.append("GEO_IMPOSSIBLE_TRAVEL")
                explanations.append(
                    f"Physical impossibility: {prev_city} -> {raw_txn['city']} "
                    f"({dist_km:,.0f} km in {elapsed_sec:.0f}s, {implied_speed_kmh:,.0f} km/h)."
                )
            elif dist_km >= 120.0 and implied_speed_kmh >= 280.0:
                geo_score = min(90.0, 45.0 + (implied_speed_kmh - 280.0) * 0.07)
                reason_codes.append("GEO_HIGH_VELOCITY_HOP")
                explanations.append(
                    f"Rapid inter-city transit: {prev_city} -> {raw_txn['city']} "
                    f"({dist_km:,.0f} km at {implied_speed_kmh:,.0f} km/h)."
                )
            elif prev_city != raw_txn["city"] and dist_km >= 80.0:
                geo_score = 22.0

        # ------------------------------------------------------------------
        # 3. Amount & Behavioural Anomaly Risk (0 - 100)
        # ------------------------------------------------------------------
        amt = float(raw_txn["amount_inr"])
        mean = float(raw_txn["card_baseline_mean"])
        std = max(float(raw_txn["card_baseline_std"]), 300.0)
        zscore = (amt - mean) / std
        amt_ratio = amt / max(mean, 1.0)

        anom_score = 0.0
        if amt_ratio >= 10.0 or zscore >= 8.0:
            anom_score = 92.0
            reason_codes.append("AMT_EXTREME_OUTLIER")
            explanations.append(
                f"Ticket {amt_ratio:.1f}x card baseline ({zscore:.1f} sigma above mean)."
            )
        elif amt_ratio >= 4.0 or zscore >= 4.0:
            anom_score = 68.0
            reason_codes.append("AMT_SIGMA_OUTLIER")
            explanations.append(f"Spend outlier: {amt_ratio:.1f}x baseline ({zscore:.1f} sigma).")
        elif amt_ratio >= 2.2:
            anom_score = 34.0

        seen_devices = {str(h["device_id"]) for h in card_hist}
        home_device_id = raw_txn.get("home_device_id")
        new_device = (bool(home_device_id) and device_id != str(home_device_id)) or (
            bool(card_hist) and (device_id not in seen_devices)
        )
        if new_device:
            anom_score = min(100.0, anom_score + 20.0)
            if amt >= 40000.0:
                reason_codes.append("NEW_DEVICE_HIGH_VALUE")
                explanations.append(f"Unseen device {device_id} on high-value authorization.")

        off_home_city = str(raw_txn["city"]) != str(raw_txn["home_city"])
        if off_home_city:
            anom_score = min(100.0, anom_score + 12.0)

        if str(raw_txn["mcc"]) in HIGH_RISK_MCCS and amt >= 60000.0:
            anom_score = min(100.0, anom_score + 15.0)
            if "AMT_EXTREME_OUTLIER" not in reason_codes and "AMT_SIGMA_OUTLIER" not in reason_codes:
                reason_codes.append("HIGH_LIQUIDITY_MCC")

        # ------------------------------------------------------------------
        # 4. Fraud Ring / Shared Entity Topology Risk (0 - 100)
        # ------------------------------------------------------------------
        dev_card_count = len(dev_cards)
        ip_card_count = len(ip_cards)
        ring_score = 0.0

        if dev_card_count >= 3:
            ring_score = min(100.0, 68.0 + (dev_card_count - 2) * 14.0)
            reason_codes.append("RING_SHARED_DEVICE")
            explanations.append(
                f"Device {device_id} shared across {dev_card_count} distinct cards in window."
            )
        elif dev_card_count == 2:
            ring_score = 52.0
            reason_codes.append("ENTITY_DEV_OVERLAP")
            explanations.append(f"Device {device_id} linked to 2 distinct cards.")

        if ip_card_count >= 3:
            ring_score = max(ring_score, min(96.0, 60.0 + (ip_card_count - 2) * 12.0))
            reason_codes.append("RING_SHARED_IP")
            explanations.append(
                f"IP hash {ip_hash} associated with {ip_card_count} distinct cards."
            )

        if entity_flagged:
            ring_score = max(ring_score, 85.0)
            reason_codes.append("PRIOR_BLOCKED_ENTITY")
            explanations.append("Device or IP previously flagged in a blocked attempt.")

        # ------------------------------------------------------------------
        # Weighted Composite + Institutional Hard Escalators
        # ------------------------------------------------------------------
        composite = (
            vel_score * self.weights["velocity"]
            + geo_score * self.weights["geo_haversine"]
            + anom_score * self.weights["anomaly"]
            + ring_score * self.weights["fraud_ring"]
        )

        # Hard deterministic escalators prevent high-confidence single-vector attacks
        # from being diluted below the block threshold.
        if geo_score >= 95.0:
            composite = max(composite, 84.0)
        if ring_score >= 78.0:
            composite = max(composite, 79.0)
        if vel_score >= 90.0:
            composite = max(composite, 78.0)
        if anom_score >= 88.0:
            if (new_device or off_home_city) and (
                str(raw_txn["mcc"]) in HIGH_RISK_MCCS or amt >= 75000.0
            ):
                composite = max(composite, 76.0)
            else:
                composite = max(composite, 48.0)

        risk_score = int(round(min(100.0, max(0.0, composite))))

        if risk_score >= self.block_threshold:
            decision = "BLOCKED"
        elif risk_score >= self.review_threshold:
            decision = "REVIEW"
        else:
            decision = "APPROVED"

        primary_signal = self._select_primary_signal(
            decision=decision,
            geo_score=geo_score,
            dist_km=dist_km,
            implied_speed_kmh=implied_speed_kmh,
            ring_score=ring_score,
            dev_card_count=dev_card_count,
            ip_card_count=ip_card_count,
            vel_score=vel_score,
            txns_60s=txns_60s,
            txns_5m=txns_5m,
            anom_score=anom_score,
            amt_ratio=amt_ratio,
        )

        if not explanations:
            explanations.append("Transaction aligns with cardholder home city, device, and spend baseline.")

        latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

        scored_txn = dict(raw_txn)
        scored_txn.update(
            {
                "risk_score": risk_score,
                "decision": decision,
                "analyst_status": "AUTO",
                "scores": {
                    "velocity": int(round(vel_score)),
                    "geo_haversine": int(round(geo_score)),
                    "anomaly": int(round(anom_score)),
                    "fraud_ring": int(round(ring_score)),
                },
                "weights": dict(self.weights),
                "telemetry": {
                    "txns_60s": txns_60s + 1,
                    "txns_5m": txns_5m + 1,
                    "spend_5m_inr": round(spend_5m, 0),
                    "prev_city": prev_city,
                    "distance_km": round(dist_km, 1),
                    "elapsed_sec": round(elapsed_sec, 1),
                    "implied_speed_kmh": round(implied_speed_kmh, 0),
                    "amount_zscore": round(zscore, 2),
                    "amount_ratio": round(amt_ratio, 2),
                    "device_linked_cards": dev_card_count,
                    "ip_linked_cards": ip_card_count,
                },
                "reason_codes": reason_codes or ["BASELINE_NOMINAL"],
                "primary_signal": primary_signal,
                "explanation": explanations,
                "latency_ms": latency_ms,
            }
        )

        self.store.record_transaction(scored_txn)
        return scored_txn

    @staticmethod
    def _select_primary_signal(
        decision: str,
        geo_score: float,
        dist_km: float,
        implied_speed_kmh: float,
        ring_score: float,
        dev_card_count: int,
        ip_card_count: int,
        vel_score: float,
        txns_60s: int,
        txns_5m: int,
        anom_score: float,
        amt_ratio: float,
    ) -> str:
        if decision == "APPROVED" and max(geo_score, ring_score, vel_score, anom_score) < 35:
            return "BASELINE NOMINAL"

        ranked = [
            (geo_score, f"GEO {dist_km:,.0f}km @ {implied_speed_kmh:,.0f}km/h"),
            (ring_score, f"RING {max(dev_card_count, ip_card_count)} CARDS LINKED"),
            (vel_score, f"VEL {txns_60s + 1}/60s ({txns_5m + 1}/5m)"),
            (anom_score, f"ANOM {amt_ratio:.1f}x BASELINE"),
        ]
        top_score, label = max(ranked, key=lambda x: x[0])
        return label if top_score >= 25 else "BASELINE NOMINAL"
