"""
Aegis — backend test suite.

Uses a temporary SQLite database so real data is never touched.
All tests run against the FastAPI TestClient (in-process, no network).
"""

import json
import os
import tempfile
import sys
from pathlib import Path

import pytest

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point the app at a temporary database BEFORE importing anything that
# calls initialize_database().
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["AEGIS_DB_PATH"] = _tmp_db.name
os.environ["AEGIS_TELEMETRY_SOURCE"] = "simulated"

from fastapi.testclient import TestClient  # noqa: E402
from src.app import app  # noqa: E402

client = TestClient(app)

# ---------------------------------------------------------------------------
# Telemetry payloads for reuse
# ---------------------------------------------------------------------------
NORMAL_TELEMETRY = {
    "cpu": 30.0,
    "memory": 40.0,
    "request_rate": 100.0,
    "latency": 80.0,
    "error_rate": 0.5,
    "db_connections": 20.0,
}

HIGH_RISK_TELEMETRY = {
    "cpu": 95.0,
    "memory": 92.0,
    "request_rate": 280.0,
    "latency": 220.0,
    "error_rate": 4.5,
    "db_connections": 70.0,
}


# ===========================================================================
# Status endpoints
# ===========================================================================

class TestRoot:
    def test_returns_200(self):
        r = client.get("/")
        assert r.status_code == 200

    def test_ok_flag(self):
        r = client.get("/")
        assert r.json()["ok"] is True

    def test_has_version(self):
        r = client.get("/")
        assert "version" in r.json()


class TestHealth:
    def test_returns_200(self):
        r = client.get("/health")
        assert r.status_code == 200

    def test_api_component_ok(self):
        r = client.get("/health")
        assert r.json()["components"]["api"]["ok"] is True

    def test_database_component_ok(self):
        r = client.get("/health")
        assert r.json()["components"]["database"]["ok"] is True

    def test_model_component_present(self):
        r = client.get("/health")
        assert "model" in r.json()["components"]


# ===========================================================================
# Telemetry
# ===========================================================================

class TestTelemetry:
    def test_returns_200(self):
        r = client.get("/telemetry")
        assert r.status_code == 200

    def test_has_all_fields(self):
        r = client.get("/telemetry")
        data = r.json()
        for field in ("cpu", "memory", "request_rate", "latency", "error_rate", "db_connections"):
            assert field in data, f"Missing field: {field}"

    def test_has_timestamp(self):
        r = client.get("/telemetry")
        assert "timestamp" in r.json()

    def test_has_source(self):
        r = client.get("/telemetry")
        assert r.json()["source"] == "simulated"

    def test_save_persists_to_history(self):
        r = client.get("/telemetry?save=true")
        assert r.status_code == 200
        h = client.get("/telemetry/history?limit=5")
        assert h.status_code == 200
        assert h.json()["count"] >= 1


# ===========================================================================
# Prediction
# ===========================================================================

class TestPredict:
    def test_normal_telemetry_returns_200(self):
        r = client.post("/predict", json=NORMAL_TELEMETRY)
        assert r.status_code == 200

    def test_response_has_required_fields(self):
        r = client.post("/predict", json=NORMAL_TELEMETRY)
        data = r.json()
        for field in ("prediction", "probability", "risk_level", "anomalies", "contributing_factors"):
            assert field in data, f"Missing field: {field}"

    def test_probability_in_range(self):
        r = client.post("/predict", json=NORMAL_TELEMETRY)
        p = r.json()["probability"]
        assert 0.0 <= p <= 1.0

    def test_risk_level_valid(self):
        r = client.post("/predict", json=NORMAL_TELEMETRY)
        assert r.json()["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_prediction_is_int(self):
        r = client.post("/predict", json=NORMAL_TELEMETRY)
        assert r.json()["prediction"] in (0, 1)

    def test_high_risk_telemetry(self):
        r = client.post("/predict", json=HIGH_RISK_TELEMETRY)
        assert r.status_code == 200
        data = r.json()
        assert data["risk_level"] == "HIGH"
        assert len(data["anomalies"]) > 0

    def test_anomalies_have_required_fields(self):
        r = client.post("/predict", json=HIGH_RISK_TELEMETRY)
        for anomaly in r.json()["anomalies"]:
            for field in ("metric", "value", "threshold", "severity", "message"):
                assert field in anomaly, f"Anomaly missing field: {field}"

    def test_contributing_factors_are_known_metrics(self):
        r = client.post("/predict", json=NORMAL_TELEMETRY)
        known = {"cpu", "memory", "request_rate", "latency", "error_rate", "db_connections"}
        for f in r.json()["contributing_factors"]:
            assert f in known

    def test_missing_field_returns_422(self):
        bad = {k: v for k, v in NORMAL_TELEMETRY.items() if k != "cpu"}
        r = client.post("/predict", json=bad)
        assert r.status_code == 422

    def test_invalid_cpu_returns_422(self):
        bad = {**NORMAL_TELEMETRY, "cpu": 150.0}  # > 100
        r = client.post("/predict", json=bad)
        assert r.status_code == 422

    def test_negative_latency_returns_422(self):
        bad = {**NORMAL_TELEMETRY, "latency": -1.0}
        r = client.post("/predict", json=bad)
        assert r.status_code == 422

    def test_prediction_creates_incident_record(self):
        before = client.get("/incidents?limit=1").json()["total"]
        client.post("/predict", json=NORMAL_TELEMETRY)
        after = client.get("/incidents?limit=1").json()["total"]
        assert after == before + 1


# ===========================================================================
# Anomaly thresholds (unit tests — risk_engine tested directly)
# ===========================================================================

class TestRiskEngine:
    def _engine(self):
        from src.risk_engine import detect_anomalies, assess_risk
        return detect_anomalies, assess_risk

    def test_no_anomaly_below_threshold(self):
        detect_anomalies, _ = self._engine()
        result = detect_anomalies({"cpu": 79.9, "memory": 50.0, "request_rate": 100.0,
                                   "latency": 100.0, "error_rate": 1.0, "db_connections": 20.0})
        assert not any(a["metric"] == "cpu" for a in result)

    def test_anomaly_at_threshold(self):
        detect_anomalies, _ = self._engine()
        result = detect_anomalies({"cpu": 80.0, "memory": 50.0, "request_rate": 100.0,
                                   "latency": 100.0, "error_rate": 1.0, "db_connections": 20.0})
        assert any(a["metric"] == "cpu" for a in result)

    def test_critical_severity_above_multiplier(self):
        detect_anomalies, _ = self._engine()
        result = detect_anomalies({"cpu": 96.0, "memory": 50.0, "request_rate": 100.0,
                                   "latency": 100.0, "error_rate": 1.0, "db_connections": 20.0})
        cpu_anomaly = next(a for a in result if a["metric"] == "cpu")
        assert cpu_anomaly["severity"] == "CRITICAL"

    def test_medium_severity_just_above_warning(self):
        detect_anomalies, _ = self._engine()
        result = detect_anomalies({"cpu": 82.0, "memory": 50.0, "request_rate": 100.0,
                                   "latency": 100.0, "error_rate": 1.0, "db_connections": 20.0})
        cpu_anomaly = next(a for a in result if a["metric"] == "cpu")
        assert cpu_anomaly["severity"] == "MEDIUM"

    def test_high_probability_gives_high_risk(self):
        _, assess_risk = self._engine()
        level, _ = assess_risk(0.85, [])
        assert level == "HIGH"

    def test_medium_probability_gives_medium_risk(self):
        _, assess_risk = self._engine()
        level, _ = assess_risk(0.6, [])
        assert level == "MEDIUM"

    def test_low_probability_no_anomalies_gives_low(self):
        _, assess_risk = self._engine()
        level, _ = assess_risk(0.1, [])
        assert level == "LOW"

    def test_critical_anomaly_overrides_to_high(self):
        _, assess_risk = self._engine()
        anomalies = [{"metric": "cpu", "value": 96.0, "severity": "CRITICAL",
                      "threshold": 80.0, "message": ""}]
        level, override = assess_risk(0.1, anomalies)
        assert level == "HIGH"
        assert override is not None

    def test_four_anomalies_override_to_high(self):
        _, assess_risk = self._engine()
        anomalies = [{"metric": f"m{i}", "value": 99.0, "severity": "MEDIUM",
                      "threshold": 80.0, "message": ""} for i in range(4)]
        level, override = assess_risk(0.1, anomalies)
        assert level == "HIGH"
        assert override is not None

    def test_invalid_probability_raises(self):
        _, assess_risk = self._engine()
        with pytest.raises(ValueError):
            assess_risk(1.5, [])


# ===========================================================================
# Incidents
# ===========================================================================

class TestIncidents:
    def test_returns_200(self):
        r = client.get("/incidents")
        assert r.status_code == 200

    def test_has_count_and_incidents(self):
        r = client.get("/incidents")
        data = r.json()
        assert "count" in data
        assert "incidents" in data
        assert isinstance(data["incidents"], list)

    def test_pagination(self):
        # Populate a few predictions first
        for _ in range(5):
            client.post("/predict", json=NORMAL_TELEMETRY)
        r1 = client.get("/incidents?limit=2&offset=0")
        r2 = client.get("/incidents?limit=2&offset=2")
        ids1 = {i["id"] for i in r1.json()["incidents"]}
        ids2 = {i["id"] for i in r2.json()["incidents"]}
        assert ids1.isdisjoint(ids2)

    def test_limit_is_respected(self):
        r = client.get("/incidents?limit=3")
        assert len(r.json()["incidents"]) <= 3


class TestActiveIncidents:
    def _ensure_open(self):
        # Create a high-risk incident so there's something to work with
        client.post("/predict", json=HIGH_RISK_TELEMETRY)

    def test_returns_200(self):
        r = client.get("/active-incidents")
        assert r.status_code == 200

    def test_invalid_status_returns_400(self):
        r = client.get("/active-incidents?status=FOOBAR")
        assert r.status_code == 400

    def test_invalid_risk_returns_400(self):
        r = client.get("/active-incidents?risk_level=EXTREME")
        assert r.status_code == 400

    def test_filter_by_status_open(self):
        self._ensure_open()
        r = client.get("/active-incidents?status=OPEN")
        assert r.status_code == 200
        for inc in r.json()["incidents"]:
            assert inc["status"] == "OPEN"

    def test_detail_not_found_returns_404(self):
        r = client.get("/active-incidents/999999")
        assert r.status_code == 404

    def test_status_transition_acknowledge(self):
        self._ensure_open()
        incidents = client.get("/active-incidents?status=OPEN&limit=1").json()["incidents"]
        if not incidents:
            pytest.skip("No open incidents to test with")
        iid = incidents[0]["id"]
        r = client.patch(
            f"/active-incidents/{iid}/status",
            json={"status": "ACKNOWLEDGED"},
        )
        assert r.status_code == 200
        assert r.json()["incident"]["status"] == "ACKNOWLEDGED"

    def test_status_transition_resolve(self):
        self._ensure_open()
        incidents = client.get("/active-incidents?status=OPEN&limit=1").json()["incidents"]
        if not incidents:
            # Try acknowledged
            incidents = client.get("/active-incidents?status=ACKNOWLEDGED&limit=1").json()["incidents"]
        if not incidents:
            pytest.skip("No open/acknowledged incidents to test with")
        iid = incidents[0]["id"]
        r = client.patch(
            f"/active-incidents/{iid}/status",
            json={"status": "RESOLVED", "resolution_notes": "Test resolution."},
        )
        assert r.status_code == 200
        assert r.json()["incident"]["status"] == "RESOLVED"

    def test_invalid_transition_returns_400(self):
        # Try to transition from CLOSED to OPEN (should fail)
        self._ensure_open()
        open_inc = client.get("/active-incidents?status=OPEN&limit=1").json()["incidents"]
        if not open_inc:
            pytest.skip("No open incidents")
        iid = open_inc[0]["id"]
        client.patch(f"/active-incidents/{iid}/status", json={"status": "CLOSED"})
        r = client.patch(f"/active-incidents/{iid}/status", json={"status": "OPEN"})
        assert r.status_code == 400

    def test_unknown_status_returns_422(self):
        r = client.patch("/active-incidents/1/status", json={"status": "BADSTATUS"})
        assert r.status_code == 422


# ===========================================================================
# Analytics
# ===========================================================================

class TestAnalytics:
    def test_summary_returns_200(self):
        r = client.get("/analytics/summary")
        assert r.status_code == 200

    def test_summary_has_required_fields(self):
        r = client.get("/analytics/summary")
        data = r.json()
        assert "total_predictions" in data
        assert "total_incidents_detected" in data
        assert "high_risk_open" in data

    def test_trends_returns_200(self):
        r = client.get("/analytics/trends")
        assert r.status_code == 200

    def test_trends_has_required_keys(self):
        r = client.get("/analytics/trends")
        data = r.json()
        assert "risk_distribution" in data
        assert "anomaly_frequency" in data


# ===========================================================================
# Model info
# ===========================================================================

class TestModelInfo:
    def test_returns_200(self):
        r = client.get("/model/info")
        assert r.status_code == 200

    def test_has_available_field(self):
        r = client.get("/model/info")
        assert "available" in r.json()

    def test_has_features_when_model_loaded(self):
        r = client.get("/model/info")
        if r.json()["available"]:
            assert "features" in r.json()


# ===========================================================================
# Settings
# ===========================================================================

class TestSettings:
    def test_thresholds_returns_200(self):
        r = client.get("/settings/thresholds")
        assert r.status_code == 200

    def test_thresholds_has_all_metrics(self):
        r = client.get("/settings/thresholds")
        thresholds = r.json()["thresholds"]
        for metric in ("cpu", "memory", "request_rate", "latency", "error_rate", "db_connections"):
            assert metric in thresholds
