"""Database connection. Credentials come ONLY from environment variables (or a local .env file)."""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

load_dotenv()  # reads .env if present; harmless if it is not


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


def build_url(database: str | None = None) -> URL:
    # URL.create escapes special characters in passwords (e.g. @ : / #) for us.
    return URL.create(
        "postgresql+psycopg",
        username=_require("PM_DB_USER"),
        password=_require("PM_DB_PASSWORD"),
        host=os.getenv("PM_DB_HOST", "localhost"),
        port=int(os.getenv("PM_DB_PORT", "5432")),
        database=database or os.getenv("PM_DB_NAME", "predictive_maintenance"),
    )


def get_engine(database: str | None = None) -> Engine:
    return create_engine(build_url(database), pool_pre_ping=True)
