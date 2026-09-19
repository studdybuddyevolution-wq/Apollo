"""Apply Apollo's additive reference-integration schema when Postgres is enabled."""

from __future__ import annotations

from pathlib import Path

from storage import STORE

_MIGRATION = Path(__file__).resolve().parent / "migrations" / "005_reference_integrations.sql"


def ensure_reference_schema() -> None:
    if not STORE or not _MIGRATION.exists():
        return
    try:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_MIGRATION.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[Apollo reference schema] warning: {exc}")
