"""Pytest fixtures: dedicated Postgres test DB + per-test transaction rollback.

The whole app is pointed at a separate ``<main>_test`` database (never the main
DB). The test schema is created by ``alembic upgrade head``. Each test runs
inside a transaction that is rolled back afterwards (savepoint-based, so the
app's own ``commit()`` does not leak), giving isolation without dropping
tables or the database.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

from app.settings import get_settings

_MAIN_URL = str(get_settings().database_url)
_parsed = urlparse(_MAIN_URL)
TEST_DB_NAME = (_parsed.path.lstrip("/") or "kvitto") + "_test"
TEST_DB_URL = urlunparse(_parsed._replace(path="/" + TEST_DB_NAME))
os.environ["DATABASE_URL"] = TEST_DB_URL
get_settings.cache_clear()

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.db import engine, get_db
from app.main import app

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_test_database() -> None:
    """Create the test database if it is missing; otherwise surface a clear error."""
    maint_url = urlunparse(urlparse(TEST_DB_URL)._replace(path="/postgres"))
    maint = create_engine(maint_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with maint.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": TEST_DB_NAME},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    except Exception as exc:
        raise RuntimeError(
            f"Could not create test database '{TEST_DB_NAME}': {exc}. "
            f"Create it manually (CREATE DATABASE {TEST_DB_NAME};) and re-run."
        ) from exc
    finally:
        maint.dispose()


def _run_migrations() -> None:
    cfg = Config(os.path.join(_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_ROOT, "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def _test_db() -> None:
    _ensure_test_database()
    _run_migrations()


@pytest.fixture()
def client(_test_db):
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    transaction.rollback()
    connection.close()
