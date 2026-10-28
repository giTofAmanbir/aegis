"""
Aegis — database layer.

Uses SQLite with parameterised queries throughout.
All schema changes are additive (ALTER TABLE IF NOT EXISTS pattern)
so the existing aegis.db and its 1354+ rows are never destroyed.

Tables
------
incidents          — full prediction history (one row per /predict call)
active_incidents   — deduplicated incident management records
telemetry_history  — rolling time-series of telemetry snapshots for charts
"""

import json
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import DB_PATH, TELEMETRY_HISTORY_LIMIT

logger = logging.getLogger(__name__)

DATABASE_PATH: Path = DB_PATH


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema initialisation and migrations
# ---------------------------------------------------------------------------

def initialize_database() -> None:
    """
    Create tables and apply safe, additive migrations.
    Never drops existing data.
    """
    with get_connection() as conn:
        # --- incidents (prediction history) ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                telemetry   TEXT    NOT NULL,
                prediction  INTEGER NOT NULL,
                probability REAL    NOT NULL,
                risk_level  TEXT    NOT NULL,
                anomalies   TEXT    NOT NULL
            )
        """)

        # --- active_incidents (incident management) ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_incidents (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint      TEXT    NOT NULL,
                first_seen       TEXT    NOT NULL,
                last_seen        TEXT    NOT NULL,
                telemetry        TEXT    NOT NULL,
                prediction       INTEGER NOT NULL,
                probability      REAL    NOT NULL,
                risk_level       TEXT    NOT NULL,
                anomalies        TEXT    NOT NULL,
                status           TEXT    NOT NULL DEFAULT 'OPEN',
                occurrence_count INTEGER NOT NULL DEFAULT 1,
                resolved_at      TEXT,
                acknowledged_at  TEXT,
                title            TEXT,
                resolution_notes TEXT,
                risk_override    TEXT
            )
        """)

        # --- telemetry_history (rolling chart data) ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT    NOT NULL,
                source       TEXT    NOT NULL DEFAULT 'local',
                cpu          REAL,
                memory       REAL,
                request_rate REAL,
                latency      REAL,
                error_rate   REAL,
                db_connections REAL
            )
        """)

        # --- Indexes ---
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_fingerprint_status
            ON active_incidents (fingerprint, status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_status
            ON active_incidents (status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_risk_level
            ON active_incidents (risk_level)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_incidents_timestamp
            ON incidents (timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_history_timestamp
            ON telemetry_history (timestamp)
        """)

        # Safe migrations for columns added after initial release
        _add_column_if_missing(conn, "active_incidents", "acknowledged_at", "TEXT")
        _add_column_if_missing(conn, "active_incidents", "title", "TEXT")
        _add_column_if_missing(conn, "active_incidents", "resolution_notes", "TEXT")
        _add_column_if_missing(conn, "active_incidents", "risk_override", "TEXT")

    logger.info("Database initialised at %s", DATABASE_PATH)


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    col_type: str,
) -> None:
    """Add a column to a table only if it does not already exist."""
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        logger.info("Migrated: added column %s.%s", table, column)


# ---------------------------------------------------------------------------
# Fingerprinting / deduplication
# ---------------------------------------------------------------------------

def _create_fingerprint(prediction: int, anomalies: list[dict]) -> str:
    """
    Stable incident signature from the prediction outcome
    and the set of metrics currently breaching their thresholds.
    """
    anomaly_metrics = sorted({
        a["metric"] for a in anomalies if "metric" in a
    })
    signature = json.dumps(
        {"prediction": int(prediction), "anomaly_metrics": anomaly_metrics},
        sort_keys=True,
    )
    return hashlib.sha256(signature.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Prediction history
# ---------------------------------------------------------------------------

def save_prediction(
    telemetry: dict,
    prediction: int,
    probability: float,
    risk_level: str,
    anomalies: list[dict],
    risk_override: str | None = None,
) -> tuple[int, int | None]:
    """
    Persist a prediction to the incidents history table.

    If an incident is detected (prediction=1 OR anomalies present),
    create or update a matching active_incident.

    Returns
    -------
    (prediction_id, active_incident_id | None)

    Deduplication policy
    --------------------
    An active incident is reused if its fingerprint matches AND its status
    is OPEN or ACKNOWLEDGED.  Resolved incidents are never reopened; a new
    active_incident is created instead.
    """
    timestamp = current_timestamp()
    prediction = int(prediction)
    probability = float(probability)
    anomalies = anomalies or []

    with get_connection() as conn:
        # Always record prediction history
        cursor = conn.execute("""
            INSERT INTO incidents
                (timestamp, telemetry, prediction, probability, risk_level, anomalies)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            json.dumps(telemetry),
            prediction,
            probability,
            risk_level,
            json.dumps(anomalies),
        ))
        prediction_id = cursor.lastrowid

        # Only create/update an active incident when something is wrong
        incident_detected = prediction == 1 or len(anomalies) > 0
        if not incident_detected:
            return prediction_id, None

        fingerprint = _create_fingerprint(prediction, anomalies)

        existing = conn.execute("""
            SELECT id, occurrence_count
            FROM active_incidents
            WHERE fingerprint = ?
              AND status IN ('OPEN', 'ACKNOWLEDGED')
            ORDER BY id DESC
            LIMIT 1
        """, (fingerprint,)).fetchone()

        if existing:
            conn.execute("""
                UPDATE active_incidents
                SET last_seen        = ?,
                    telemetry        = ?,
                    prediction       = ?,
                    probability      = ?,
                    risk_level       = ?,
                    anomalies        = ?,
                    risk_override    = ?,
                    occurrence_count = occurrence_count + 1
                WHERE id = ?
            """, (
                timestamp,
                json.dumps(telemetry),
                prediction,
                probability,
                risk_level,
                json.dumps(anomalies),
                risk_override,
                existing["id"],
            ))
            active_id = existing["id"]
        else:
            cursor2 = conn.execute("""
                INSERT INTO active_incidents (
                    fingerprint, first_seen, last_seen,
                    telemetry, prediction, probability,
                    risk_level, anomalies, risk_override,
                    status, occurrence_count, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 1, NULL)
            """, (
                fingerprint,
                timestamp,
                timestamp,
                json.dumps(telemetry),
                prediction,
                probability,
                risk_level,
                json.dumps(anomalies),
                risk_override,
            ))
            active_id = cursor2.lastrowid

    return prediction_id, active_id


# For backwards compatibility with any existing callers
def save_incident(
    telemetry,
    prediction,
    probability,
    risk_level,
    anomalies,
):
    pred_id, _ = save_prediction(
        telemetry=telemetry,
        prediction=prediction,
        probability=probability,
        risk_level=risk_level,
        anomalies=anomalies,
    )
    return pred_id


# ---------------------------------------------------------------------------
# Prediction / incident history queries
# ---------------------------------------------------------------------------

def _deserialise_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("telemetry", "anomalies"):
        if field in d and isinstance(d[field], str):
            d[field] = json.loads(d[field])
    return d


def get_prediction_history(
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Full prediction log (incidents table)."""
    limit = max(1, min(int(limit), 200))
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM incidents
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        return [_deserialise_row(r) for r in rows]


def get_incident_history(limit: int = 50) -> list[dict]:
    """Backwards-compatible alias."""
    return get_prediction_history(limit=limit)


def get_total_predictions() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]


# ---------------------------------------------------------------------------
# Active incident queries
# ---------------------------------------------------------------------------

VALID_STATUSES = {"OPEN", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"}


def get_active_incidents(
    status: str | None = None,
    risk_level: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(int(limit), 200))

    if status is not None:
        status = status.upper()
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. "
                f"Valid values: {sorted(VALID_STATUSES)}"
            )

    if risk_level is not None:
        risk_level = risk_level.upper()
        if risk_level not in {"HIGH", "MEDIUM", "LOW"}:
            raise ValueError("Invalid risk_level. Valid: HIGH, MEDIUM, LOW")

    conditions = []
    params: list = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if risk_level:
        conditions.append("risk_level = ?")
        params.append(risk_level)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT * FROM active_incidents
            {where}
            ORDER BY last_seen DESC
            LIMIT ? OFFSET ?
        """, params).fetchall()
        return [_deserialise_row(r) for r in rows]


def get_active_incident_by_id(incident_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM active_incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        return _deserialise_row(row) if row else None


def get_active_incident_counts() -> dict:
    """Returns counts by status and by risk level."""
    with get_connection() as conn:
        status_rows = conn.execute("""
            SELECT status, COUNT(*) as cnt
            FROM active_incidents
            GROUP BY status
        """).fetchall()
        risk_rows = conn.execute("""
            SELECT risk_level, COUNT(*) as cnt
            FROM active_incidents
            WHERE status NOT IN ('RESOLVED', 'CLOSED')
            GROUP BY risk_level
        """).fetchall()

    return {
        "by_status": {r["status"]: r["cnt"] for r in status_rows},
        "by_risk": {r["risk_level"]: r["cnt"] for r in risk_rows},
    }


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

# Allowed transitions: current status -> set of permitted next statuses
VALID_TRANSITIONS: dict[str, set[str]] = {
    "OPEN":          {"ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"},
    "ACKNOWLEDGED":  {"INVESTIGATING", "RESOLVED", "CLOSED"},
    "INVESTIGATING": {"RESOLVED", "CLOSED"},
    "RESOLVED":      {"CLOSED"},
    "CLOSED":        set(),
}


def update_incident_status(
    incident_id: int,
    new_status: str,
    resolution_notes: str | None = None,
) -> tuple[bool, str]:
    """
    Apply a status transition to an active incident.

    Returns (success, message).
    success=False means the incident was not found or the transition is invalid.
    """
    new_status = new_status.upper()
    if new_status not in VALID_STATUSES:
        return False, f"Unknown status '{new_status}'."

    incident = get_active_incident_by_id(incident_id)
    if incident is None:
        return False, f"Incident {incident_id} not found."

    current = incident["status"]
    allowed = VALID_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        return (
            False,
            f"Cannot transition from {current} to {new_status}. "
            f"Allowed transitions from {current}: {sorted(allowed) or 'none'}.",
        )

    timestamp = current_timestamp()
    updates = {"status": new_status}

    if new_status == "ACKNOWLEDGED":
        updates["acknowledged_at"] = timestamp
    if new_status in ("RESOLVED", "CLOSED"):
        updates["resolved_at"] = timestamp
        if resolution_notes is not None:
            updates["resolution_notes"] = resolution_notes

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [incident_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE active_incidents SET {set_clause} WHERE id = ?",
            values,
        )

    return True, f"Incident {incident_id} transitioned to {new_status}."


# Backwards-compatible helpers
def acknowledge_incident(incident_id: int) -> bool:
    success, _ = update_incident_status(incident_id, "ACKNOWLEDGED")
    return success


def resolve_incident(incident_id: int) -> bool:
    success, _ = update_incident_status(incident_id, "RESOLVED")
    return success


# ---------------------------------------------------------------------------
# Telemetry history
# ---------------------------------------------------------------------------

def save_telemetry_snapshot(snapshot: dict) -> None:
    """
    Persist a telemetry snapshot for trend charts.
    Trims the table to TELEMETRY_HISTORY_LIMIT rows after each insert.
    """
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO telemetry_history
                (timestamp, source, cpu, memory, request_rate,
                 latency, error_rate, db_connections)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot.get("timestamp", current_timestamp()),
            snapshot.get("source", "local"),
            snapshot.get("cpu"),
            snapshot.get("memory"),
            snapshot.get("request_rate"),
            snapshot.get("latency"),
            snapshot.get("error_rate"),
            snapshot.get("db_connections"),
        ))

        # Keep the table at a manageable size
        conn.execute("""
            DELETE FROM telemetry_history
            WHERE id NOT IN (
                SELECT id FROM telemetry_history
                ORDER BY id DESC
                LIMIT ?
            )
        """, (TELEMETRY_HISTORY_LIMIT,))


def get_telemetry_history(limit: int = 100) -> list[dict]:
    limit = max(1, min(int(limit), 500))
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM telemetry_history
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_analytics_summary() -> dict:
    """Aggregate metrics for the dashboard overview."""
    with get_connection() as conn:
        total_predictions = conn.execute(
            "SELECT COUNT(*) FROM incidents"
        ).fetchone()[0]

        total_incidents_detected = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE prediction = 1"
        ).fetchone()[0]

        active_counts = get_active_incident_counts()

        high_risk_open = conn.execute("""
            SELECT COUNT(*) FROM active_incidents
            WHERE risk_level = 'HIGH'
              AND status NOT IN ('RESOLVED', 'CLOSED')
        """).fetchone()[0]

        avg_probability = conn.execute(
            "SELECT AVG(probability) FROM incidents"
        ).fetchone()[0]

        recent_incidents = conn.execute("""
            SELECT * FROM active_incidents
            ORDER BY last_seen DESC
            LIMIT 5
        """).fetchall()

    return {
        "total_predictions": total_predictions,
        "total_incidents_detected": total_incidents_detected,
        "active_incident_counts": active_counts,
        "high_risk_open": high_risk_open,
        "average_probability": round(avg_probability or 0, 4),
        "recent_incidents": [_deserialise_row(r) for r in recent_incidents],
    }


def get_analytics_trends(limit: int = 100) -> dict:
    """Time-series data for dashboard charts."""
    limit = max(1, min(int(limit), 500))

    with get_connection() as conn:
        telemetry_rows = conn.execute("""
            SELECT * FROM telemetry_history
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,)).fetchall()

        incident_rows = conn.execute("""
            SELECT DATE(first_seen) as date, COUNT(*) as count,
                   risk_level
            FROM active_incidents
            GROUP BY DATE(first_seen), risk_level
            ORDER BY date ASC
            LIMIT ?
        """, (limit,)).fetchall()

        risk_dist = conn.execute("""
            SELECT risk_level, COUNT(*) as count
            FROM active_incidents
            GROUP BY risk_level
        """).fetchall()

        anomaly_freq = conn.execute("""
            SELECT anomalies FROM incidents
            ORDER BY id DESC
            LIMIT 200
        """).fetchall()

    # Count anomaly frequency by metric
    metric_counts: dict[str, int] = {}
    for row in anomaly_freq:
        try:
            for a in json.loads(row["anomalies"]):
                m = a.get("metric", "unknown")
                metric_counts[m] = metric_counts.get(m, 0) + 1
        except Exception:
            pass

    return {
        "telemetry_history": [dict(r) for r in telemetry_rows],
        "incident_by_date": [dict(r) for r in incident_rows],
        "risk_distribution": [dict(r) for r in risk_dist],
        "anomaly_frequency": [
            {"metric": m, "count": c}
            for m, c in sorted(metric_counts.items(), key=lambda x: -x[1])
        ],
    }


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
initialize_database()
