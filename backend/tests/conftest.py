"""Test fixtures: in-memory SQLite + seeded dataset."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Force SQLite for tests BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite:///./test_spaceship.db"

from app.data.importer import import_csv  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402

CSV_PATH = Path(__file__).parent.parent.parent / "data" / "mock_logistics_data.csv"


@pytest.fixture(scope="session", autouse=True)
def _seed_db():
    # Recreate from scratch
    db_path = Path("test_spaceship.db")
    if db_path.exists():
        db_path.unlink()
    Base.metadata.create_all(bind=engine)
    import_csv(CSV_PATH)
    yield
    # cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture()
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
