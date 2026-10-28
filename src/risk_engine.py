"""
Aegis — anomaly detection and risk classification engine.

Thresholds and risk rules are documented and configurable.
All anomaly objects contain enough information for the frontend
to display a clear explanation without further backend calls.

Risk classification logic
--------------------------
HIGH   — model probability ≥ 0.80  OR  critical-severity anomaly present
         OR  4+ anomalies simultaneously
MEDIUM — model probability ≥ 0.50  OR  2+ anomalies
LOW    — everything else

When a risk override is applied (e.g. a single CRITICAL anomaly forces HIGH)
the response includes a `risk_override` field explaining the reason.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------
# Each entry: metric -> (warning_threshold, critical_multiplier)
# An anomaly is detected when value >= warning_threshold.
# Severity is CRITICAL when value >= warning_threshold * critical_multiplier,
# otherwise MEDIUM.
#
# These values are calibrated for demonstration purposes and should be
# adjusted to match real infrastructure baselines.

THRESHOLDS: dict[str, dict] = {
    "cpu": {
        "warning": 80.0,
        "critical_multiplier": 1.2,   # 96 %
        "unit": "%",
        "description": "CPU utilisation",
    },
    "memory": {
        "warning": 85.0,
        "critical_multiplier": 1.15,  # ~97.75 %
        "unit": "%",
        "description": "Memory utilisation",
    },
    "request_rate": {
        "warning": 200.0,
        "critical_multiplier": 1.5,   # 300 req/s
        "unit": "req/s",
        "description": "Incoming request rate",
    },
    "latency": {
        "warning": 180.0,
        "critical_multiplier": 1.5,   # 270 ms
        "unit": "ms",
        "description": "Average request latency",
    },
    "error_rate": {
        "warning": 3.0,
        "critical_multiplier": 1.67,  # 5.0 %
        "unit": "%",
        "description": "Request error rate",
    },
    "db_connections": {
        "warning": 50.0,
        "critical_multiplier": 1.6,   # 80
        "unit": "count",
        "description": "Active database connections",
    },
}


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def detect_anomalies(telemetry: dict) -> list[dict]:
    """
    Return a list of anomaly objects for any metric that meets or exceeds
    its configured warning threshold.

    Each anomaly contains:
        metric      str    metric name
        value       float  observed value
        threshold   float  warning threshold
        severity    str    "CRITICAL" | "MEDIUM"
        unit        str    measurement unit
        message     str    human-readable explanation
    """
    anomalies: list[dict] = []

    for metric, cfg in THRESHOLDS.items():
        raw = telemetry.get(metric)
        if raw is None:
            continue

        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning("Non-numeric value for metric %s: %r", metric, raw)
            continue

        warning = cfg["warning"]
        if value < warning:
            continue

        critical_threshold = warning * cfg["critical_multiplier"]
        severity = "CRITICAL" if value >= critical_threshold else "MEDIUM"

        anomalies.append({
            "metric": metric,
            "value": round(value, 4),
            "threshold": warning,
            "critical_threshold": round(critical_threshold, 4),
            "severity": severity,
            "unit": cfg["unit"],
            "description": cfg["description"],
            "message": (
                f"{cfg['description']} is {value}{cfg['unit']}, "
                f"{'critically ' if severity == 'CRITICAL' else ''}exceeding "
                f"the {'critical' if severity == 'CRITICAL' else 'warning'} "
                f"threshold of "
                f"{critical_threshold if severity == 'CRITICAL' else warning}"
                f"{cfg['unit']}."
            ),
        })

    return anomalies


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------

def assess_risk(
    probability: float,
    anomalies: list[dict] | None = None,
) -> tuple[str, str | None]:
    """
    Calculate the overall risk level and return the reason for any override.

    Args:
        probability: ML-predicted incident probability (0.0 – 1.0).
        anomalies:   Anomaly list from detect_anomalies().

    Returns:
        (risk_level, override_reason)
        risk_level      "HIGH" | "MEDIUM" | "LOW"
        override_reason str | None  — set when anomaly severity forced an upgrade

    Raises:
        ValueError if probability is outside [0, 1].
    """
    if not (0.0 <= probability <= 1.0):
        raise ValueError(
            f"Probability must be between 0 and 1; received {probability!r}."
        )

    anomalies = anomalies or []
    anomaly_count = len(anomalies)
    has_critical = any(a.get("severity") == "CRITICAL" for a in anomalies)

    override_reason: str | None = None

    # Determine base level from model probability
    if probability >= 0.80:
        base_level = "HIGH"
    elif probability >= 0.50:
        base_level = "MEDIUM"
    else:
        base_level = "LOW"

    # Upgrade rules
    if base_level != "HIGH":
        if has_critical:
            override_reason = (
                "Risk upgraded to HIGH because a CRITICAL-severity anomaly "
                "was detected."
            )
            return "HIGH", override_reason
        if anomaly_count >= 4:
            override_reason = (
                f"Risk upgraded to HIGH because {anomaly_count} simultaneous "
                "anomalies were detected (threshold: 4)."
            )
            return "HIGH", override_reason

    if base_level == "LOW":
        if anomaly_count >= 2:
            override_reason = (
                f"Risk upgraded to MEDIUM because {anomaly_count} anomalies "
                "were detected (threshold: 2)."
            )
            return "MEDIUM", override_reason

    return base_level, override_reason


def get_thresholds() -> dict:
    """Return the active threshold configuration (for /settings and /model/info)."""
    return {
        metric: {
            "warning": cfg["warning"],
            "critical": round(cfg["warning"] * cfg["critical_multiplier"], 4),
            "unit": cfg["unit"],
            "description": cfg["description"],
        }
        for metric, cfg in THRESHOLDS.items()
    }
