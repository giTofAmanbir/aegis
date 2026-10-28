"""
Aegis — FastAPI application.

All endpoints return consistent JSON structures.
Telemetry collection and prediction are separate operations:
  GET  /telemetry  — read-only; does NOT create any database records.
  POST /predict    — explicit prediction; persists results.

This prevents the auto-predict-on-every-poll problem.
"""

import logging
import random
from datetime import datetime, timezone

import psutil
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from database import (
    get_prediction_history,
    get_total_predictions,
    get_active_incidents,
    get_active_incident_by_id,
    get_active_incident_counts,
    update_incident_status,
    save_prediction,
    save_telemetry_snapshot,
    get_telemetry_history,
    get_analytics_summary,
    get_analytics_trends,
    VALID_STATUSES,
)
from src.config import ALLOWED_ORIGINS, TELEMETRY_SOURCE
from src.predictor import (
    predict_incident,
    is_model_available,
    get_model_error,
    get_model_info,
)
from src.risk_engine import assess_risk, detect_anomalies, get_thresholds

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("aegis.api")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Aegis Incident Prediction API",
    description=(
        "AI-powered infrastructure observability and incident intelligence platform. "
        "Monitors system telemetry, detects anomalies, predicts incidents, "
        "and tracks operational risk."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TelemetryInput(BaseModel):
    """Six telemetry metrics accepted by the ML model."""

    cpu: float = Field(..., ge=0, le=100, description="CPU utilisation (%)")
    memory: float = Field(..., ge=0, le=100, description="Memory utilisation (%)")
    request_rate: float = Field(..., ge=0, description="Request rate (req/s)")
    latency: float = Field(..., ge=0, description="Latency (ms)")
    error_rate: float = Field(..., ge=0, le=100, description="Error rate (%)")
    db_connections: float = Field(..., ge=0, description="DB connection count")

    @field_validator("cpu", "memory", "request_rate", "latency", "error_rate", "db_connections", mode="before")
    @classmethod
    def must_be_finite(cls, v):
        import math
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise ValueError("Telemetry values must be finite numbers.")
        return v


class StatusUpdate(BaseModel):
    status: str = Field(
        ...,
        description="New status: OPEN, ACKNOWLEDGED, INVESTIGATING, RESOLVED, CLOSED",
    )
    resolution_notes: str | None = Field(
        None,
        max_length=2000,
        description="Optional notes; recommended when resolving or closing.",
    )

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v):
        up = v.upper()
        if up not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Valid values: {sorted(VALID_STATUSES)}"
            )
        return up


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ok(data: dict) -> dict:
    """Wrap data in a consistent success envelope."""
    return {"ok": True, **data}


def _collect_telemetry() -> dict:
    """
    Build a telemetry snapshot.

    CPU and memory are real measurements from psutil.
    request_rate, latency, error_rate, and db_connections are simulated
    because they require integration with an application instrumentation layer.

    The 'source' field identifies which metrics are real vs simulated.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    if TELEMETRY_SOURCE == "simulated":
        return {
            "timestamp": timestamp,
            "source": "simulated",
            "cpu": round(random.uniform(10, 95), 2),
            "memory": round(random.uniform(30, 90), 2),
            "request_rate": round(random.uniform(50, 300), 2),
            "latency": round(random.uniform(30, 250), 2),
            "error_rate": round(random.uniform(0.05, 5.0), 3),
            "db_connections": random.randint(5, 80),
        }

    # "local" — real CPU/memory, simulated application metrics
    return {
        "timestamp": timestamp,
        "source": "local",
        "source_detail": {
            "cpu": "psutil (real)",
            "memory": "psutil (real)",
            "request_rate": "simulated — requires application instrumentation",
            "latency": "simulated — requires application instrumentation",
            "error_rate": "simulated — requires application instrumentation",
            "db_connections": "simulated — requires application instrumentation",
        },
        "cpu": psutil.cpu_percent(interval=0.1),
        "memory": psutil.virtual_memory().percent,
        "request_rate": round(random.uniform(80, 250), 2),
        "latency": round(random.uniform(50, 200), 2),
        "error_rate": round(random.uniform(0.1, 4.0), 3),
        "db_connections": random.randint(10, 60),
    }


# ---------------------------------------------------------------------------
# Routes — status
# ---------------------------------------------------------------------------

@app.get("/", tags=["Status"])
def root():
    return _ok({
        "application": "Aegis",
        "description": "AI-powered infrastructure incident prediction platform",
        "version": "2.0.0",
        "docs": "/docs",
    })


@app.get("/health", tags=["Status"])
def health():
    """
    Returns the operational status of each component.
    A 200 response with ok=True means the API is running.
    Check individual component fields for deeper health.
    """
    model_ok = is_model_available()
    db_ok = False
    try:
        get_total_predictions()
        db_ok = True
    except Exception as exc:
        logger.error("Health check — DB error: %s", exc)

    all_ok = model_ok and db_ok

    return {
        "ok": all_ok,
        "status": "healthy" if all_ok else "degraded",
        "components": {
            "api": {"ok": True},
            "database": {"ok": db_ok},
            "model": {
                "ok": model_ok,
                "error": get_model_error() if not model_ok else None,
            },
            "telemetry_source": TELEMETRY_SOURCE,
        },
    }


# ---------------------------------------------------------------------------
# Routes — telemetry (read-only, does NOT create DB records)
# ---------------------------------------------------------------------------

@app.get("/telemetry", tags=["Telemetry"])
def get_telemetry(save: bool = Query(False, description="Persist snapshot to history")):
    """
    Return current telemetry. Does NOT run a prediction or save an incident.
    Set save=true to persist the snapshot to the telemetry_history table.
    """
    snapshot = _collect_telemetry()
    if save:
        try:
            save_telemetry_snapshot(snapshot)
        except Exception as exc:
            logger.error("Failed to save telemetry snapshot: %s", exc)
    return snapshot


@app.get("/telemetry/history", tags=["Telemetry"])
def telemetry_history(limit: int = Query(100, ge=1, le=500)):
    """Return stored telemetry snapshots for time-series charts."""
    rows = get_telemetry_history(limit=limit)
    return _ok({"count": len(rows), "history": rows})


# ---------------------------------------------------------------------------
# Routes — prediction
# ---------------------------------------------------------------------------

@app.post("/predict", tags=["Prediction"])
def predict(data: TelemetryInput):
    """
    Run ML inference on the supplied telemetry.
    Persists the result and creates/updates an active incident when warranted.

    This is an explicit operation — it does NOT run automatically on telemetry polls.
    """
    if not is_model_available():
        raise HTTPException(
            status_code=503,
            detail=f"Model is not available: {get_model_error()}",
        )

    telemetry = data.model_dump()

    try:
        ml_result = predict_incident(**telemetry)
    except Exception as exc:
        logger.error("Prediction failed: %s", exc)
        raise HTTPException(status_code=500, detail="Prediction failed.") from exc

    probability = ml_result["probability"]
    prediction = ml_result["prediction"]
    contributing_factors = ml_result["contributing_factors"]

    anomalies = detect_anomalies(telemetry)
    risk_level, risk_override = assess_risk(probability, anomalies)

    try:
        prediction_id, active_incident_id = save_prediction(
            telemetry=telemetry,
            prediction=prediction,
            probability=probability,
            risk_level=risk_level,
            anomalies=anomalies,
            risk_override=risk_override,
        )
    except Exception as exc:
        logger.error("Failed to persist prediction: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save prediction.") from exc

    return _ok({
        "prediction_id": prediction_id,
        "active_incident_id": active_incident_id,
        "prediction": prediction,
        "probability": round(probability, 6),
        "risk_level": risk_level,
        "risk_override": risk_override,
        "anomalies": anomalies,
        "contributing_factors": contributing_factors,
        "model_info": {"type": "RandomForestClassifier"},
    })


# ---------------------------------------------------------------------------
# Routes — model
# ---------------------------------------------------------------------------

@app.get("/model/info", tags=["Model"])
def model_info():
    return _ok(get_model_info())


# ---------------------------------------------------------------------------
# Routes — incidents (prediction history)
# ---------------------------------------------------------------------------

@app.get("/incidents", tags=["Incidents"])
def list_incidents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return prediction history (all /predict calls)."""
    incidents = get_prediction_history(limit=limit, offset=offset)
    total = get_total_predictions()
    return _ok({
        "total": total,
        "count": len(incidents),
        "offset": offset,
        "limit": limit,
        "incidents": incidents,
    })


# ---------------------------------------------------------------------------
# Routes — active incidents (incident management)
# ---------------------------------------------------------------------------

@app.get("/active-incidents", tags=["Incident Management"])
def list_active_incidents(
    status: str | None = Query(None, description="Filter by status"),
    risk_level: str | None = Query(None, description="Filter by risk level"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return active incidents with optional status/risk filtering and pagination."""
    try:
        incidents = get_active_incidents(
            status=status,
            risk_level=risk_level,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    counts = get_active_incident_counts()
    return _ok({
        "count": len(incidents),
        "offset": offset,
        "limit": limit,
        "summary": counts,
        "incidents": incidents,
    })


@app.get("/active-incidents/{incident_id}", tags=["Incident Management"])
def get_incident_detail(incident_id: int):
    """Return full details of a single active incident."""
    incident = get_active_incident_by_id(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=404,
            detail=f"Active incident {incident_id} not found.",
        )
    return _ok({"incident": incident})


@app.patch("/active-incidents/{incident_id}/status", tags=["Incident Management"])
def patch_incident_status(incident_id: int, body: StatusUpdate):
    """
    Transition an incident to a new status.

    Valid transitions:
      OPEN → ACKNOWLEDGED, INVESTIGATING, RESOLVED, CLOSED
      ACKNOWLEDGED → INVESTIGATING, RESOLVED, CLOSED
      INVESTIGATING → RESOLVED, CLOSED
      RESOLVED → CLOSED
      CLOSED → (no further transitions)
    """
    success, message = update_incident_status(
        incident_id=incident_id,
        new_status=body.status,
        resolution_notes=body.resolution_notes,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)

    incident = get_active_incident_by_id(incident_id)
    return _ok({"message": message, "incident": incident})


# Keep old endpoints for backwards compatibility
@app.patch("/incidents/{incident_id}/acknowledge", tags=["Incident Management"], deprecated=True)
def acknowledge_endpoint(incident_id: int):
    success, msg = update_incident_status(incident_id, "ACKNOWLEDGED")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"incident_id": incident_id, "status": "ACKNOWLEDGED", "message": msg})


@app.patch("/incidents/{incident_id}/resolve", tags=["Incident Management"], deprecated=True)
def resolve_endpoint(incident_id: int):
    success, msg = update_incident_status(incident_id, "RESOLVED")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"incident_id": incident_id, "status": "RESOLVED", "message": msg})


# ---------------------------------------------------------------------------
# Routes — analytics
# ---------------------------------------------------------------------------

@app.get("/analytics/summary", tags=["Analytics"])
def analytics_summary():
    """Aggregate metrics for the dashboard overview panel."""
    try:
        summary = get_analytics_summary()
    except Exception as exc:
        logger.error("Analytics summary error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute analytics.") from exc
    return _ok(summary)


@app.get("/analytics/trends", tags=["Analytics"])
def analytics_trends(limit: int = Query(100, ge=1, le=500)):
    """Time-series data for dashboard charts."""
    try:
        trends = get_analytics_trends(limit=limit)
    except Exception as exc:
        logger.error("Analytics trends error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute trends.") from exc
    return _ok(trends)


# ---------------------------------------------------------------------------
# Routes — settings / configuration info
# ---------------------------------------------------------------------------

@app.get("/settings/thresholds", tags=["Settings"])
def settings_thresholds():
    """Return the active anomaly detection thresholds."""
    return _ok({
        "thresholds": get_thresholds(),
        "note": (
            "Thresholds are currently hardcoded. "
            "Configurable thresholds via PUT will be added in a future release."
        ),
    })
