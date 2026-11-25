# SentinelPay — Real-Time Transaction Fraud Monitor

An institutional-grade real-time payment fraud operations console built as a single-service Python + Streamlit application for zero-sleep deployment on Streamlit Community Cloud.
*#streamlit Link:*
  
https://sentinelpay-fraud-monitor.streamlit.app/
## Architecture Overview

- **Single-Service Zero-Sleep Runtime (`app.py`)**: Unifies the live Indian payment stream, weighted fraud-scoring engine, entity-link graph builder, and SOC analyst console inside one Streamlit process with `@st.fragment` partial refreshes.
- **Resilient Hybrid State Layer (`fraud_engine.py`)**: Uses Upstash Redis (`UPSTASH_REDIS_URL` from environment, `.env`, or `st.secrets`) for sliding-window velocity, geo-history, and entity-link state, with automatic fallback to `st.session_state` in-memory sliding windows when no Redis URL is configured.
- **Weighted Risk-Scoring Engine (`fraud_engine.py`)**:
  - **Velocity (25%)**: 60s and 5m burst cadence plus card-testing micro-probe + cash-out detection.
  - **Geo-Haversine (30%)**: Great-circle distance and implied transit velocity (`km/h`) across Indian cities.
  - **Spend & Behavioural Anomaly (25%)**: Cardholder baseline z-score/ratio, unseen device detection, city drift, and high-liquidity MCC flags.
  - **Fraud Ring Topology (20%)**: Multi-card collisions on shared device fingerprints or IP hashes.
- **Indian Payment Simulator (`simulator.py`)**: Formats currency in Indian Rupees (`₹1,45,000`), generates realistic masked Indian bank BINs (`4532 •••• •••• 8841`), exact coordinates across Mumbai, Bengaluru, Delhi NCR, Hyderabad, Chennai, Kolkata, Pune, and Kurnool, and includes 4 on-demand attack injectors:
  1. `IMPOSSIBLE_TRAVEL`
  2. `VELOCITY_BURST`
  3. `FRAUD_RING`
  4. `ATO_ANOMALY`
- **Entity-Relationship Graph (`graph_builder.py`)**: NetworkX + Plotly topology visualizing `Card <-> Device <-> IP <-> Merchant` linkages and highlighting active ring clusters.

## Project Structure

```text
sentinelpay-fraud-monitor/
├── app.py                  # Enterprise SOC dashboard, custom CSS, and stream controller
├── fraud_engine.py         # Weighted risk-scoring engine (Velocity, Haversine, Anomaly, Ring)
├── simulator.py            # Realistic Indian payment generator + Attack Scenario injectors
├── graph_builder.py        # Clean NetworkX + Plotly entity-relationship topology graph
├── requirements.txt        # Pinned lightweight dependencies
├── .streamlit/
│   └── config.toml         # Institutional dark-slate theme configuration
└── README.md               # Local setup and Streamlit Cloud deployment documentation
