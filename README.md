# Aegis — AI Infrastructure Incident Prediction Platform

> AI-powered infrastructure observability and incident intelligence.
> Monitors system telemetry, detects anomalies, predicts incidents, and tracks operational risk.

---

## Architecture

```
Browser ─► React (Vite) ─► FastAPI ─► SQLite
                              │
                              ├─► RandomForestClassifier (aegis_model.pkl)
                              ├─► Risk Engine (threshold + ML)
                              └─► Telemetry (psutil + simulated)
```

**Backend:** Python 3.11 · FastAPI · Uvicorn · scikit-learn · SQLite  
**Frontend:** React 19 · Vite · Recharts · Lucide React

---

## Quick Start (Windows)

### 1 — Activate the Python virtual environment

```powershell
.venv\Scripts\Activate.ps1
```

### 2 — Install backend dependencies

```powershell
pip install -r requirements.txt
```

### 3 — Start the FastAPI backend

```powershell
.venv\Scripts\uvicorn.exe src.app:app --reload --host 127.0.0.1 --port 8000
```

### 4 — Install frontend dependencies (first run only)

```powershell
cd frontend
npm install
```

### 5 — Start the Vite dev server

```powershell
cd frontend
npm run dev
```

---

## URLs

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API | http://127.0.0.1:8000 |
| API Docs (Swagger) | http://127.0.0.1:8000/docs |
| API Docs (Redoc) | http://127.0.0.1:8000/redoc |

---

## Running Tests

```powershell
# From project root, with venv active
.venv\Scripts\python.exe -m pytest tests/test_api.py -v
```

Tests use a temporary database — your real `aegis.db` is never touched.

## Build the Frontend

```powershell
cd frontend
npm run build
```

---

## Configuration

Copy `.env.example` to `.env` in the project root and adjust as needed:

```env
AEGIS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
AEGIS_DB_PATH=aegis.db
AEGIS_MODEL_PATH=src/aegis_model.pkl
AEGIS_TELEMETRY_SOURCE=local     # "local" or "simulated"
AEGIS_TELEMETRY_HISTORY_LIMIT=500
```

Frontend API URL is set in `frontend/.env`:
```env
VITE_API_URL=http://127.0.0.1:8000
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API status |
| GET | `/health` | Component health check |
| GET | `/telemetry` | Live telemetry (read-only) |
| GET | `/telemetry/history` | Stored telemetry for charts |
| POST | `/predict` | Run ML prediction (creates incident record) |
| GET | `/incidents` | Full prediction history |
| GET | `/active-incidents` | Incident management list |
| GET | `/active-incidents/{id}` | Incident detail |
| PATCH | `/active-incidents/{id}/status` | Update incident status |
| GET | `/analytics/summary` | Dashboard KPIs |
| GET | `/analytics/trends` | Time-series chart data |
| GET | `/model/info` | Model metadata and feature importances |
| GET | `/settings/thresholds` | Active anomaly thresholds |

---

## Dashboard Views

- **Overview** — KPI stats, live telemetry, recent incidents, system health
- **Monitoring** — Real-time metrics with threshold indicators and historical charts
- **Prediction** — Manual telemetry input form with ML model result, anomaly list, contributing factors
- **Incidents** — Filterable/searchable incident table with lifecycle management (Acknowledge → Investigate → Resolve → Close)
- **Analytics** — Risk distribution pie, anomaly frequency bar chart, incidents-over-time stacked bar
- **Settings** — Model info, feature importances, threshold configuration, runtime config

---

## How It Works

1. **Telemetry** — `GET /telemetry` returns live CPU/memory (via psutil) + simulated application metrics. This is **read-only** and does not create database records.

2. **Prediction** — `POST /predict` runs the RandomForestClassifier on six metrics, detects threshold anomalies, and computes risk level. Results are saved to the `incidents` table (prediction history).

3. **Deduplication** — If an incident is detected (prediction=1 or anomalies present), a fingerprint is computed from the prediction + anomaly metric set. If an active incident with the same fingerprint exists, it's updated rather than duplicated.

4. **Lifecycle** — Active incidents flow through: `OPEN → ACKNOWLEDGED → INVESTIGATING → RESOLVED → CLOSED`. Invalid transitions are rejected.

5. **Risk** — Risk = MAX(model probability bands, anomaly count/severity rules). A CRITICAL anomaly forces HIGH regardless of model output.

---

## Known Limitations

- `request_rate`, `latency`, `error_rate`, and `db_connections` are **simulated** values. They require integration with an application metrics layer or Prometheus for real data.
- The model was trained on synthetic data. Performance on real production traffic has not been validated.
- Authentication is not implemented. This is a portfolio/development deployment.
- Threshold updates are read-only in the current version (configurable via `risk_engine.py`).

---

## Project Structure

```
Aegis/
├── src/
│   ├── app.py          — FastAPI application and all API routes
│   ├── config.py       — Environment configuration loader
│   ├── predictor.py    — ML model loading and inference
│   ├── risk_engine.py  — Anomaly detection and risk classification
│   └── aegis_model.pkl — Trained RandomForestClassifier
├── database.py         — SQLite layer: schema, queries, migrations
├── tests/
│   └── test_api.py     — 56-test backend test suite
├── frontend/
│   └── src/
│       ├── App.jsx     — Complete 6-view React dashboard
│       ├── App.css     — Design system (dark theme, all tokens)
│       └── main.jsx    — React entry point
├── data/               — Training CSV files
├── notebooks/          — day1.ipynb (training notebook)
├── requirements.txt
├── .env.example
└── README.md
```
