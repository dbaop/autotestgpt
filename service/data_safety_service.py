"""
Data safety net: auto-backup MySQL to local SQLite on every startup,
and auto-restore when MySQL is detected as empty (e.g. Docker container
restarted without a persistent volume).

Rationale:
  The user's MySQL is at 192.168.162.137 — likely a Docker container.
  If the container restarts without a volume mount, ALL data is lost.
  This service keeps a local SQLite mirror so data survives MySQL resets.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import Flask
from sqlalchemy import create_engine, text, inspect

logger = logging.getLogger(__name__)

# Local backup lives alongside the SQLite instance directory
BACKUP_DIR = Path(__file__).resolve().parents[1] / "instance" / "backups"
BACKUP_DB_NAME = "autotestgpt_backup.db"


def _is_mysql_empty(mysql_engine) -> bool:
    """Return True if MySQL has only bootstrapped/default data (effectively empty)."""
    try:
        with mysql_engine.connect() as conn:
            req_count = conn.execute(text("SELECT COUNT(*) FROM requirements")).fetchone()[0]
            kb_count = conn.execute(text("SELECT COUNT(*) FROM knowledge_bases")).fetchone()[0]
            case_count = conn.execute(text("SELECT COUNT(*) FROM test_cases")).fetchone()[0]
            # Empty = nothing beyond the auto-created default project + maybe 1 requirement
            return req_count <= 1 and kb_count == 0 and case_count == 0
    except Exception:
        return False


def _has_backup() -> bool:
    backup_path = BACKUP_DIR / BACKUP_DB_NAME
    return backup_path.exists() and backup_path.stat().st_size > 0


def _row_counts(engine) -> dict[str, int]:
    tables = [
        "projects", "requirements", "knowledge_bases", "knowledge_entries",
        "test_cases", "test_scripts", "execution_records",
        "conversations", "messages", "agent_configs", "agent_events",
    ]
    counts = {}
    with engine.connect() as conn:
        for t in tables:
            try:
                counts[t] = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).fetchone()[0]
            except Exception:
                counts[t] = 0
    return counts


def backup_mysql_to_sqlite(mysql_uri: str) -> bool:
    """Copy all rows from MySQL to local SQLite backup."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / BACKUP_DB_NAME
    backup_uri = f"sqlite:///{backup_path}"

    mysql_engine = create_engine(mysql_uri, pool_pre_ping=True)
    backup_engine = create_engine(backup_uri)

    try:
        inspector = inspect(mysql_engine)
        mysql_tables = inspector.get_table_names()

        with mysql_engine.connect() as mysql_conn, backup_engine.connect() as backup_conn:
            # Create backup tables to match MySQL
            for table_name in mysql_tables:
                cols = inspector.get_columns(table_name)
                col_defs = []
                for col in cols:
                    col_type = str(col["type"])
                    # Map MySQL types to SQLite-compatible types
                    if "INT" in col_type.upper():
                        col_type = "INTEGER"
                    elif "VARCHAR" in col_type.upper() or "TEXT" in col_type.upper():
                        col_type = "TEXT"
                    elif "DATETIME" in col_type.upper() or "TIMESTAMP" in col_type.upper():
                        col_type = "TEXT"
                    elif "FLOAT" in col_type.upper() or "DOUBLE" in col_type.upper():
                        col_type = "REAL"
                    elif "BOOL" in col_type.upper():
                        col_type = "INTEGER"
                    elif "JSON" in col_type.upper():
                        col_type = "TEXT"
                    nullable = "" if col.get("nullable", True) else "NOT NULL"
                    pk = "PRIMARY KEY" if col.get("primary_key") else ""
                    col_defs.append(f'"{col["name"]}" {col_type} {nullable} {pk}'.strip())

                create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'
                backup_conn.execute(text(create_sql))

            backup_conn.commit()

            # Copy data table by table
            total = 0
            for table_name in mysql_tables:
                try:
                    rows = mysql_conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
                    if not rows:
                        continue
                    col_names = [col["name"] for col in inspector.get_columns(table_name)]
                    # Clear existing data in backup table
                    backup_conn.execute(text(f"DELETE FROM {table_name}"))
                    # Insert
                    placeholders = ", ".join([f":{c}" for c in col_names])
                    col_str = ", ".join(col_names)
                    for row in rows:
                        row_dict = dict(zip(col_names, row))
                        backup_conn.execute(
                            text(f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders})"),
                            row_dict,
                        )
                    total += len(rows)
                except Exception as exc:
                    logger.warning("Backup of table %s failed: %s", table_name, exc)

            backup_conn.commit()

        # Write metadata
        meta_path = BACKUP_DIR / "backup_meta.txt"
        meta_path.write_text(
            f"backup_at={datetime.now(timezone.utc).isoformat()}\n"
            f"total_rows={total}\n"
            f"mysql_uri={mysql_uri.split('@')[1] if '@' in mysql_uri else mysql_uri}\n"
        )

        logger.info("Backup complete: %d rows saved to %s", total, backup_path)
        return True

    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        return False
    finally:
        mysql_engine.dispose()
        backup_engine.dispose()


def restore_sqlite_to_mysql(mysql_uri: str) -> Optional[dict[str, int]]:
    """Restore data from local SQLite backup into MySQL. Returns row counts."""
    backup_path = BACKUP_DIR / BACKUP_DB_NAME
    if not backup_path.exists():
        return None

    backup_uri = f"sqlite:///{backup_path}"
    mysql_engine = create_engine(mysql_uri, pool_pre_ping=True)
    backup_engine = create_engine(backup_uri)

    try:
        inspector = inspect(backup_engine)
        backup_tables = inspector.get_table_names()

        with backup_engine.connect() as backup_conn, mysql_engine.connect() as mysql_conn:
            # Disable FK checks during restore
            try:
                mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                mysql_conn.commit()
            except Exception:
                pass

            restored = {}
            for table_name in backup_tables:
                try:
                    rows = backup_conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
                    if not rows:
                        continue
                    col_names = [col["name"] for col in inspector.get_columns(table_name)]

                    # Check which rows already exist in MySQL
                    mysql_ids = set()
                    try:
                        id_rows = mysql_conn.execute(text(f"SELECT id FROM {table_name}")).fetchall()
                        mysql_ids = {r[0] for r in id_rows}
                    except Exception:
                        pass

                    new_rows = [r for r in rows if r[0] not in mysql_ids]
                    if not new_rows:
                        continue

                    placeholders = ", ".join([f":{c}" for c in col_names])
                    col_str = ", ".join(col_names)
                    count = 0
                    for row in new_rows:
                        row_dict = dict(zip(col_names, row))
                        try:
                            mysql_conn.execute(
                                text(f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders})"),
                                row_dict,
                            )
                            count += 1
                        except Exception:
                            pass

                    mysql_conn.commit()
                    if count > 0:
                        restored[table_name] = count
                        logger.info("Restored %d rows to %s", count, table_name)
                except Exception as exc:
                    logger.warning("Restore of table %s skipped: %s", table_name, exc)

            try:
                mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
                mysql_conn.commit()
            except Exception:
                pass

        logger.info("Restore complete: %s", restored)
        return restored

    except Exception as exc:
        logger.error("Restore failed: %s", exc)
        return None
    finally:
        mysql_engine.dispose()
        backup_engine.dispose()


def run_startup_safety_check(mysql_uri: str, app: Flask) -> bool:
    """Run at app startup. Back up MySQL → SQLite. Restore if MySQL is empty."""
    is_mysql = "mysql" in mysql_uri.lower()
    if not is_mysql:
        return True

    mysql_engine = create_engine(mysql_uri, pool_pre_ping=True)

    try:
        if _is_mysql_empty(mysql_engine):
            app.logger.warning("MySQL appears EMPTY (no user data). Checking for local backup...")
            if _has_backup():
                app.logger.warning("Local backup found — restoring data to MySQL...")
                restored = restore_sqlite_to_mysql(mysql_uri)
                if restored:
                    total = sum(restored.values())
                    app.logger.warning(
                        "RESTORED %d rows from local backup to MySQL. "
                        "Your MySQL container likely restarted without a volume mount. "
                        "Data has been recovered from the local SQLite mirror.",
                        total,
                    )
                else:
                    app.logger.warning("Restore returned no data — backup may be empty.")
            else:
                app.logger.warning(
                    "No local backup found. If you previously had data in MySQL, "
                    "it may have been lost due to a container restart without a volume mount."
                )
        else:
            # MySQL has data — back it up
            counts = _row_counts(mysql_engine)
            app.logger.info("MySQL has data (%d requirements, %d KBs). Creating local backup...",
                           counts.get("requirements", 0), counts.get("knowledge_bases", 0))
            backup_mysql_to_sqlite(mysql_uri)
            app.logger.info("Local backup created at %s", BACKUP_DIR / BACKUP_DB_NAME)

        return True
    except Exception as exc:
        app.logger.error("Startup safety check failed: %s", exc)
        return False
    finally:
        mysql_engine.dispose()
