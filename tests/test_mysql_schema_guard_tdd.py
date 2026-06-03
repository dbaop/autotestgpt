import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.schema_guard import allows_schema_bootstrap


def test_mysql_schema_bootstrap_is_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_MYSQL_SCHEMA_BOOTSTRAP", raising=False)

    assert allows_schema_bootstrap("mysql") is False


def test_mysql_schema_bootstrap_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("ALLOW_MYSQL_SCHEMA_BOOTSTRAP", "true")

    assert allows_schema_bootstrap("mysql") is True


def test_sqlite_schema_bootstrap_keeps_existing_dev_behavior(monkeypatch):
    monkeypatch.delenv("ALLOW_MYSQL_SCHEMA_BOOTSTRAP", raising=False)

    assert allows_schema_bootstrap("sqlite") is True


def test_main_blocks_implicit_mysql_bootstrap_before_create_all():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "allows_schema_bootstrap(db.engine.dialect.name)" in source
    assert "schema_bootstrap_blocked_message()" in source


def test_main_redacts_database_uri_in_startup_banner():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "render_as_string(hide_password=True)" in source
    assert "Config.DATABASE_URI.split('://')" not in source
