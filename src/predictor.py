"""
Aegis — ML inference module.

Loads the trained RandomForestClassifier and exposes a single
predict_incident() function used by the API layer.

The model is loaded once at import time.  If the artifact is
missing the module raises a clear error rather than failing
silently inside a request handler.
"""

import logging
from pathlib import Path

import joblib
import pandas as pd

from src.config import MODEL_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature contract — order must match training data
# ---------------------------------------------------------------------------
FEATURES: list[str] = [
    "cpu",
    "memory",
    "request_rate",
    "latency",
    "error_rate",
    "db_connections",
]

# Feature metadata for the /model/info endpoint
FEATURE_META: dict[str, dict] = {
    "cpu":            {"unit": "%",      "description": "CPU utilisation (0–100)"},
    "memory":         {"unit": "%",      "description": "Memory utilisation (0–100)"},
    "request_rate":   {"unit": "req/s",  "description": "Incoming request rate"},
    "latency":        {"unit": "ms",     "description": "Average request latency"},
    "error_rate":     {"unit": "%",      "description": "Fraction of requests that returned an error"},
    "db_connections": {"unit": "count",  "description": "Active database connections"},
}

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
_model = None
_model_load_error: str | None = None


def _load_model():
    global _model, _model_load_error
    try:
        _model = joblib.load(MODEL_PATH)
        logger.info("Model loaded from %s", MODEL_PATH)
    except Exception as exc:
        _model_load_error = str(exc)
        logger.error("Failed to load model from %s: %s", MODEL_PATH, exc)


_load_model()


def is_model_available() -> bool:
    return _model is not None


def get_model_error() -> str | None:
    return _model_load_error


def get_model_info() -> dict:
    """Return metadata about the loaded model for the /model/info endpoint."""
    if _model is None:
        return {
            "available": False,
            "error": _model_load_error,
            "model_path": str(MODEL_PATH),
        }

    info: dict = {
        "available": True,
        "model_type": type(_model).__name__,
        "model_path": str(MODEL_PATH),
        "features": FEATURES,
        "feature_meta": FEATURE_META,
        "n_estimators": getattr(_model, "n_estimators", None),
        "max_depth": getattr(_model, "max_depth", None),
    }

    if hasattr(_model, "feature_importances_"):
        importances = _model.feature_importances_.tolist()
        info["feature_importances"] = dict(zip(FEATURES, importances))

    if hasattr(_model, "classes_"):
        info["classes"] = _model.classes_.tolist()

    return info


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def predict_incident(
    cpu: float,
    memory: float,
    request_rate: float,
    latency: float,
    error_rate: float,
    db_connections: float,
) -> dict:
    """
    Run ML inference for the supplied telemetry values.

    Returns:
        prediction      int   1 = incident predicted, 0 = normal
        probability     float incident probability (0.0 – 1.0)
        contributing_factors  list[str]  top-3 features by importance
        model_available bool

    Raises:
        RuntimeError if the model is not loaded.
    """
    if _model is None:
        raise RuntimeError(
            f"Model is not available: {_model_load_error or 'unknown error'}"
        )

    data = pd.DataFrame([{
        "cpu": float(cpu),
        "memory": float(memory),
        "request_rate": float(request_rate),
        "latency": float(latency),
        "error_rate": float(error_rate),
        "db_connections": float(db_connections),
    }])[FEATURES]  # enforce column order

    probability: float = float(_model.predict_proba(data)[0][1])
    prediction: int = int(probability >= 0.5)

    # Top-3 features by global importance (not instance-level SHAP)
    contributing_factors: list[str] = []
    if hasattr(_model, "feature_importances_"):
        importances = _model.feature_importances_
        ranked = sorted(
            zip(FEATURES, importances),
            key=lambda x: x[1],
            reverse=True,
        )
        contributing_factors = [f for f, _ in ranked[:3]]

    return {
        "prediction": prediction,
        "probability": probability,
        "contributing_factors": contributing_factors,
        "model_available": True,
    }
