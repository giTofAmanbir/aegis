"""
Aegis — configuration loader.

All environment-specific values live here.
Set them via .env (copy from .env.example) or the shell environment.
Never hardcode values in other modules.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (the directory that contains this file's parent)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


def _split_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


# CORS — accepted frontend origins
ALLOWED_ORIGINS: list[str] = _split_origins(
    os.getenv(
        "AEGIS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
)

# SQLite database path
DB_PATH: Path = Path(
    os.getenv("AEGIS_DB_PATH", str(_project_root / "aegis.db"))
).resolve()

# Trained model artifact path
MODEL_PATH: Path = Path(
    os.getenv("AEGIS_MODEL_PATH", str(_project_root / "src" / "aegis_model.pkl"))
).resolve()

# Telemetry source: "local" or "simulated"
TELEMETRY_SOURCE: str = os.getenv("AEGIS_TELEMETRY_SOURCE", "local").lower()

# Number of telemetry snapshots retained in the rolling history table
TELEMETRY_HISTORY_LIMIT: int = int(
    os.getenv("AEGIS_TELEMETRY_HISTORY_LIMIT", "500")
)
