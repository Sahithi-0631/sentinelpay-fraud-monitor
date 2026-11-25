"""
SentinelPay Indian Payment Stream Simulator & Attack Scenario Injectors.

Generates realistic Indian payment transactions across major Indian cities,
masked Indian bank BIN card numbers, realistic merchants, and deterministic
attack scenario bursts for SOC validation.
"""

from __future__ import annotations

import hashlib
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))


def format_inr(amount: float, show_decimals: bool = False) -> str:
    """Format a numeric amount in Indian Rupees with Indian comma grouping."""
    sign = "-" if amount < 0 else ""
    val = abs(float(amount))
    if show_decimals:
        int_part, dec_part = f"{val:.2f}".split(".")
    else:
        int_part = str(int(round(val)))
        dec_part = ""

    if len(int_part) <= 3:
        grouped = int_part
    else:
        last_three = int_part[-3:]
        rest = int_part[:-3]
        parts: List[str] = []
        while len(rest) > 2:
            parts.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.append(rest)
        grouped = ",".join(reversed(parts)) + "," + last_three

    suffix = f".{dec_part}" if show_decimals else ""
    return f"{sign}₹{grouped}{suffix}"


def format_ist_time(epoch_ts: float) -> str:
    """Format epoch seconds as HH:MM:SS.mmm IST."""
    dt = datetime.fromtimestamp(epoch_ts, tz=IST)
    return dt.strftime("%H:%M:%S.") + f"{int(dt.microsecond / 1000):03d} IST"


INDIAN_CITIES: Dict[str, Tuple[float, float]] = {
    "Mumbai": (19.0760, 72.8777),
    "Bengaluru": (12.9716, 77.5946),
    "Delhi NCR": (28.6139, 77.2090),
    "Hyderabad": (17.3850, 78.4867),
    "Chennai": (13.0827, 80.2707),
    "Kolkata": (22.5726, 88.3639),
    "Pune": (18.5204, 73.8567),
    "Kurnool": (15.8281, 78.0373),
}

INDIAN_BINS: List[Tuple[str, str]] = [
    ("4532", "HDFC Visa"),
    ("4214", "ICICI Visa"),
    ("4375", "Axis Visa"),
    ("4628", "SBI Visa"),
    ("5241", "HDFC Mastercard"),
    ("5419", "ICICI Mastercard"),
    ("5522", "Kotak Mastercard"),
    ("6521", "SBI RuPay"),
    ("6074", "PNB RuPay"),
    ("6081", "Canara RuPay"),
]

MERCHANTS: List[Dict[str, object]] = [
    {
        "name": "Croma Retail Mumbai",
        "mcc": "Electronics",
        "range": (2400, 145000),
        "channels": ["POS_EMV", "ECOM_3DS", "TOKEN_TAP"],
        "cities": ["Mumbai", "Pune"],
        "high_liquidity": True,
    },
    {
        "name": "Tanishq Jewellers",
        "mcc": "Jewellery",
        "range": (18000, 385000),
        "channels": ["POS_EMV", "ECOM_3DS"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": True,
    },
    {
        "name": "MakeMyTrip Flights",
        "mcc": "Airlines",
        "range": (3800, 88000),
        "channels": ["ECOM_3DS", "UPI_RUPAY"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": True,
    },
    {
        "name": "Swiggy Instamart",
        "mcc": "Groceries",
        "range": (180, 3400),
        "channels": ["UPI_RUPAY", "ECOM_3DS", "TOKEN_TAP"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": False,
    },
    {
        "name": "Reliance Digital",
        "mcc": "Electronics",
        "range": (1900, 165000),
        "channels": ["POS_EMV", "ECOM_3DS", "TOKEN_TAP"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": True,
    },
    {
        "name": "Flipkart Marketplace",
        "mcc": "E-Commerce",
        "range": (450, 58000),
        "channels": ["ECOM_3DS", "UPI_RUPAY"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": False,
    },
    {
        "name": "Apollo Pharmacy",
        "mcc": "Pharmacy",
        "range": (140, 4800),
        "channels": ["POS_EMV", "UPI_RUPAY", "TOKEN_TAP"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": False,
    },
    {
        "name": "Zomato Hyperpure",
        "mcc": "Dining & Supply",
        "range": (320, 12500),
        "channels": ["UPI_RUPAY", "ECOM_3DS"],
        "cities": ["Mumbai", "Bengaluru", "Delhi NCR", "Hyderabad", "Pune"],
        "high_liquidity": False,
    },
    {
        "name": "Tata CLiQ Luxury",
        "mcc": "Luxury Retail",
        "range": (6500, 195000),
        "channels": ["ECOM_3DS"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": True,
    },
    {
        "name": "IndiGo Airlines",
        "mcc": "Airlines",
        "range": (3200, 54000),
        "channels": ["ECOM_3DS", "UPI_RUPAY"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": True,
    },
    {
        "name": "BigBasket Daily",
        "mcc": "Groceries",
        "range": (220, 4200),
        "channels": ["UPI_RUPAY", "ECOM_3DS"],
        "cities": ["Mumbai", "Bengaluru", "Delhi NCR", "Hyderabad", "Chennai", "Pune"],
        "high_liquidity": False,
    },
    {
        "name": "DMart Ready",
        "mcc": "Groceries",
        "range": (350, 6800),
        "channels": ["POS_EMV", "UPI_RUPAY"],
        "cities": ["Mumbai", "Pune", "Hyderabad", "Bengaluru", "Kurnool"],
        "high_liquidity": False,
    },
    {
        "name": "Paytm Utility Bill",
        "mcc": "Utilities",
        "range": (499, 18500),
        "channels": ["UPI_RUPAY", "ECOM_3DS"],
        "cities": list(INDIAN_CITIES.keys()),
        "high_liquidity": False,
    },
]


@dataclass
class CardholderProfile:
    """Synthetic Indian cardholder identity with stable behavioural baseline."""

    card_id: str
    customer_id: str
    card_masked: str
    card_network: str
    home_city: str
    device_id: str
    ip_hash: str
    baseline_mean: float
    baseline_std: float


def _short_hash(seed: str, prefix: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{digest}"


def _build_cardholder_pool(count: int = 48, seed: int = 2026) -> List[CardholderProfile]:
    rng = random.Random(seed)
    city_names = list(INDIAN_CITIES.keys())
    city_weights = [0.22, 0.20, 0.20, 0.12, 0.08, 0.07, 0.07, 0.04]
    profiles: List[CardholderProfile] = []

    for idx in range(1, count + 1):
        bin_prefix, network = rng.choice(INDIAN_BINS)
        last4 = f"{rng.randint(1000, 9999)}"
        card_masked = f"{bin_prefix} •••• •••• {last4}"
        home_city = rng.choices(city_names, weights=city_weights, k=1)[0]

        # Tiered spending baselines (everyday consumer vs affluent spender)
        tier = rng.random()
        if tier < 0.65:
            mean_amt = rng.uniform(950, 4200)
            std_amt = mean_amt * 0.45
        elif tier < 0.90:
            mean_amt = rng.uniform(4500, 14500)
            std_amt = mean_amt * 0.42
        else:
            mean_amt = rng.uniform(16000, 42000)
            std_amt = mean_amt * 0.40

        profiles.append(
            CardholderProfile(
                card_id=f"CARD-{idx:03d}",
                customer_id=f"CUST-{1000 + idx}",
                card_masked=card_masked,
                card_network=network,
                home_city=home_city,
                device_id=_short_hash(f"dev-seed-{idx}", "DEV"),
                ip_hash=_short_hash(f"ip-seed-{idx}-{home_city}", "IP"),
                baseline_mean=round(mean_amt, 2),
                baseline_std=round(max(std_amt, 400.0), 2),
            )
        )
    return profiles


class IndianPaymentSimulator:
    """Produces realistic baseline transactions and targeted attack injections."""

    def __init__(self, seed: int = 2026) -> None:
        self._rng = random.Random(seed)
        self.profiles: List[CardholderProfile] = _build_cardholder_pool(48, seed=seed)
        self._seq = 0

    def _next_txn_id(self) -> str:
        self._seq += 1
        token = uuid.uuid4().hex[:6].upper()
        return f"TXN-{token}{self._seq % 100:02d}"

    def _jitter_coords(self, city: str, spread_deg: float = 0.035) -> Tuple[float, float]:
        base_lat, base_lon = INDIAN_CITIES[city]
        lat = round(base_lat + self._rng.uniform(-spread_deg, spread_deg), 4)
        lon = round(base_lon + self._rng.uniform(-spread_deg, spread_deg), 4)
        return lat, lon

    def _pick_merchant(self, city: str, high_liquidity_only: bool = False) -> Dict[str, object]:
        candidates = [
            m
            for m in MERCHANTS
            if (city in m["cities"]) and (not high_liquidity_only or m["high_liquidity"])
        ]
        if not candidates:
            candidates = [m for m in MERCHANTS if not high_liquidity_only or m["high_liquidity"]]
        return self._rng.choice(candidates)

    def _make_txn(
        self,
        profile: CardholderProfile,
        city: str,
        merchant: Dict[str, object],
        amount_inr: float,
        timestamp: float,
        device_id: Optional[str] = None,
        ip_hash: Optional[str] = None,
        channel: Optional[str] = None,
        scenario: str = "NORMAL",
    ) -> Dict[str, object]:
        lat, lon = self._jitter_coords(city)
        amt = round(max(amount_inr, 49.0), 0)
        chosen_channel = channel or str(self._rng.choice(merchant["channels"]))  # type: ignore[arg-type]
        return {
            "txn_id": self._next_txn_id(),
            "timestamp": float(timestamp),
            "ts_ist": format_ist_time(timestamp),
            "card_id": profile.card_id,
            "customer_id": profile.customer_id,
            "card_masked": profile.card_masked,
            "card_network": profile.card_network,
            "amount_inr": amt,
            "amount_formatted": format_inr(amt),
            "merchant": str(merchant["name"]),
            "mcc": str(merchant["mcc"]),
            "channel": chosen_channel,
            "city": city,
            "lat": lat,
            "lon": lon,
            "device_id": device_id or profile.device_id,
            "ip_hash": ip_hash or profile.ip_hash,
            "scenario": scenario,
            "card_baseline_mean": profile.baseline_mean,
            "card_baseline_std": profile.baseline_std,
            "home_city": profile.home_city,
            "home_device_id": profile.device_id,
        }

    def generate_normal_txn(self, now_ts: Optional[float] = None, organic_noise_rate: float = 0.08) -> Dict[str, object]:
        """Generate a single realistic baseline transaction (with configurable organic anomalies)."""
        ts = now_ts if now_ts is not None else time.time()
        profile = self._rng.choice(self.profiles)
        city = profile.home_city

        # Small organic chance of legitimate domestic travel or mild anomaly
        roll = self._rng.random()
        if roll < organic_noise_rate * 0.45:
            # Organic elevated purchase
            merchant = self._pick_merchant(city, high_liquidity_only=True)
            low, high = merchant["range"]  # type: ignore[misc]
            amount = self._rng.uniform(max(float(low), profile.baseline_mean * 2.5), float(high) * 0.85)
            return self._make_txn(profile, city, merchant, amount, ts)

        if roll < organic_noise_rate:
            # Organic mild travel or alternate device
            other_cities = [c for c in INDIAN_CITIES if c != city]
            travel_city = self._rng.choice(other_cities)
            merchant = self._pick_merchant(travel_city)
            amount = max(150.0, self._rng.gauss(profile.baseline_mean, profile.baseline_std))
            return self._make_txn(
                profile,
                travel_city,
                merchant,
                amount,
                ts,
                device_id=_short_hash(f"alt-{uuid.uuid4().hex}", "DEV") if self._rng.random() < 0.35 else profile.device_id,
            )

        # Clean nominal transaction
        merchant = self._pick_merchant(city)
        low, high = merchant["range"]  # type: ignore[misc]
        raw_amt = self._rng.gauss(profile.baseline_mean, profile.baseline_std * 0.75)
        clamped = min(max(raw_amt, float(low)), min(float(high), profile.baseline_mean * 2.2))
        return self._make_txn(profile, city, merchant, clamped, ts)

    def inject_impossible_travel(
        self,
        now_ts: Optional[float] = None,
        recent_card_cities: Optional[Dict[str, Tuple[str, float]]] = None,
    ) -> List[Dict[str, object]]:
        """
        Inject an impossible-travel attack pair or hop.
        If the chosen card already has a recent city, hops to a distant city (>900 km);
        otherwise generates an anchor txn followed 12 seconds later by a distant high-value txn.
        """
        ts = now_ts if now_ts is not None else time.time()
        far_pairs = [
            ("Mumbai", "Delhi NCR"),
            ("Bengaluru", "Delhi NCR"),
            ("Kurnool", "Mumbai"),
            ("Chennai", "Kolkata"),
            ("Hyderabad", "Delhi NCR"),
            ("Pune", "Kolkata"),
        ]

        if recent_card_cities:
            candidate_cards = [p for p in self.profiles if p.card_id in recent_card_cities]
        else:
            candidate_cards = []

        txns: List[Dict[str, object]] = []
        if candidate_cards:
            profile = self._rng.choice(candidate_cards)
            origin_city, origin_ts = recent_card_cities[profile.card_id]  # type: ignore[index]
            distant_options = [
                c for c in INDIAN_CITIES
                if abs(INDIAN_CITIES[c][0] - INDIAN_CITIES[origin_city][0]) > 4.5
                or abs(INDIAN_CITIES[c][1] - INDIAN_CITIES[origin_city][1]) > 4.5
            ]
            target_city = self._rng.choice(distant_options or ["Delhi NCR", "Kolkata"])
            hop_ts = max(ts, origin_ts + 8.0)
        else:
            origin_city, target_city = self._rng.choice(far_pairs)
            profile = self._rng.choice(self.profiles)
            anchor_merchant = self._pick_merchant(origin_city, high_liquidity_only=False)
            txns.append(
                self._make_txn(
                    profile,
                    origin_city,
                    anchor_merchant,
                    self._rng.uniform(450, 2200),
                    ts - 14.0,
                    scenario="NORMAL",
                )
            )
            hop_ts = ts

        attack_merchant = self._pick_merchant(target_city, high_liquidity_only=True)
        attack_amt = self._rng.uniform(78000, 245000)
        txns.append(
            self._make_txn(
                profile,
                target_city,
                attack_merchant,
                attack_amt,
                hop_ts,
                device_id=_short_hash(f"spoof-{uuid.uuid4().hex}", "DEV"),
                ip_hash=_short_hash(f"vpn-{uuid.uuid4().hex}", "IP"),
                channel="ECOM_3DS",
                scenario="IMPOSSIBLE_TRAVEL",
            )
        )
        return txns

    def inject_velocity_burst(self, now_ts: Optional[float] = None) -> List[Dict[str, object]]:
        """Inject a 5-txn card-testing + cash-out velocity burst within ~18 seconds."""
        ts = now_ts if now_ts is not None else time.time()
        profile = self._rng.choice(self.profiles)
        city = profile.home_city
        spoof_dev = _short_hash(f"bot-{uuid.uuid4().hex}", "DEV")
        spoof_ip = _short_hash(f"botip-{uuid.uuid4().hex}", "IP")

        probes = [149.0, 249.0, 199.0, 499.0]
        probe_merchants = [
            m for m in MERCHANTS if m["name"] in ("Swiggy Instamart", "Paytm Utility Bill", "Flipkart Marketplace")
        ]
        txns: List[Dict[str, object]] = []
        for idx, amt in enumerate(probes):
            merchant = self._rng.choice(probe_merchants)
            txns.append(
                self._make_txn(
                    profile,
                    city,
                    merchant,
                    amt,
                    ts - 16.0 + idx * 3.0,
                    device_id=spoof_dev,
                    ip_hash=spoof_ip,
                    channel="ECOM_3DS",
                    scenario="VELOCITY_BURST",
                )
            )

        # Final high-value cash-out attempt
        cashout_merchant = self._pick_merchant(city, high_liquidity_only=True)
        txns.append(
            self._make_txn(
                profile,
                city,
                cashout_merchant,
                self._rng.uniform(95000, 185000),
                ts,
                device_id=spoof_dev,
                ip_hash=spoof_ip,
                channel="ECOM_3DS",
                scenario="VELOCITY_BURST",
            )
        )
        return txns

    def inject_fraud_ring(self, now_ts: Optional[float] = None) -> List[Dict[str, object]]:
        """Inject an organized fraud ring: 5 distinct cards hitting 1 shared emulator device & IP."""
        ts = now_ts if now_ts is not None else time.time()
        ring_profiles = self._rng.sample(self.profiles, k=5)
        ring_device = _short_hash(f"ring-emu-{uuid.uuid4().hex}", "DEV")
        ring_ip = _short_hash(f"ring-proxy-{uuid.uuid4().hex}", "IP")
        target_cities = ["Mumbai", "Bengaluru", "Hyderabad", "Kurnool", "Delhi NCR"]

        txns: List[Dict[str, object]] = []
        for idx, profile in enumerate(ring_profiles):
            city = target_cities[idx % len(target_cities)]
            merchant = self._pick_merchant(city, high_liquidity_only=True)
            amt = self._rng.uniform(42000, 195000)
            txns.append(
                self._make_txn(
                    profile,
                    city,
                    merchant,
                    amt,
                    ts - (4 - idx) * 2.5,
                    device_id=ring_device,
                    ip_hash=ring_ip,
                    channel="ECOM_3DS",
                    scenario="FRAUD_RING",
                )
            )
        return txns

    def inject_ato_anomaly(self, now_ts: Optional[float] = None) -> List[Dict[str, object]]:
        """Inject a high-severity Account Takeover spend outlier on a low-ticket cardholder."""
        ts = now_ts if now_ts is not None else time.time()
        low_ticket_profiles = sorted(self.profiles, key=lambda p: p.baseline_mean)[:12]
        profile = self._rng.choice(low_ticket_profiles)
        other_cities = [c for c in INDIAN_CITIES if c != profile.home_city]
        city = self._rng.choice(other_cities)
        jewellery = next(m for m in MERCHANTS if m["name"] == "Tanishq Jewellers")
        amt = self._rng.uniform(195000, 365000)
        return [
            self._make_txn(
                profile,
                city,
                jewellery,
                amt,
                ts,
                device_id=_short_hash(f"ato-dev-{uuid.uuid4().hex}", "DEV"),
                ip_hash=_short_hash(f"ato-ip-{uuid.uuid4().hex}", "IP"),
                channel="ECOM_3DS",
                scenario="ATO_ANOMALY",
            )
        ]

    def seed_initial_history(self, count: int = 24) -> List[Dict[str, object]]:
        """Generate a clean chronological seed batch spanning the last ~3 minutes."""
        now = time.time()
        batch: List[Dict[str, object]] = []
        for idx in range(count):
            t = now - (count - idx) * 6.5
            batch.append(self.generate_normal_txn(now_ts=t, organic_noise_rate=0.06))
        return batch
