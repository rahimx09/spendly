"""Shared pytest fixtures for Spendly tests.

Each test gets a fresh SQLite database at a tmp_path location so the
real `expense_tracker.db` at the project root is never touched. The
`app` fixture returns the real `app.app` from `app.py`; the
`DB_PATH` monkey-patch redirects every `get_db()` call inside the
app to the temp file.
"""
import pytest

from database import db as db_module
from database.db import init_db


@pytest.fixture
def app_with_tmp_db(tmp_path, monkeypatch):
    """Yield the path to a freshly-initialised temp database."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    init_db()
    yield db_file
    # tmp_path cleanup is automatic.


@pytest.fixture
def app(app_with_tmp_db):
    """pytest-flask-compatible `app` fixture.

    The default pytest-flask fixture would try to discover `app.py`
    but use the real DB_PATH. By depending on `app_with_tmp_db`
    first, we guarantee the DB is rerouted before the first
    request hits the app.
    """
    from app import app as flask_app
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    """Flask test client bound to the temp-DB app."""
    return app.test_client()
