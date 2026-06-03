"""
One-shot migration: copy data from SQLite to MySQL.

Usage: python scripts/migrate_sqlite_to_mysql.py

Disables FK checks during migration so rows can be inserted in any order.
Skips tables that don't exist in SQLite (older schema).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text, inspect
from config import Config

SQLITE_PATH = ROOT / "instance" / "autotestgpt.db"
MYSQL_URI = Config.DATABASE_URI

if not SQLITE_PATH.exists():
    print(f"SQLite file not found: {SQLITE_PATH}")
    sys.exit(1)

sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}")
mysql_engine = create_engine(MYSQL_URI)

# Tables to migrate (dependency order — parent before child)
TABLES = [
    "projects",
    "requirements",
    "knowledge_bases",
    "knowledge_entries",
    "test_cases",
    "test_suites",
    "test_scripts",
    "execution_records",
    "conversations",
    "messages",
    "code_review_tasks",
    "code_review_findings",
    "defect_candidates",
    "final_reports",
    "fix_suggestions",
    "agent_configs",
    "agent_events",
]


def get_columns(engine, table_name: str) -> list[str]:
    insp = inspect(engine)
    try:
        return [col["name"] for col in insp.get_columns(table_name)]
    except Exception:
        return []


def sqlite_row_count(sqlite_conn, table_name: str) -> int:
    cols = get_columns(sqlite_engine, table_name)
    if not cols:
        return -1
    return sqlite_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).fetchone()[0]


def migrate_table(table_name: str, sqlite_conn, mysql_conn):
    cols = get_columns(sqlite_engine, table_name)
    if not cols:
        print(f"  [SKIP] {table_name}: table does not exist in SQLite (older schema)")
        return 0

    rows = sqlite_conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
    if not rows:
        print(f"  [SKIP] {table_name}: 0 rows in SQLite")
        return 0

    # Only migrate rows whose IDs don't already exist in MySQL
    mysql_ids = set()
    try:
        id_rows = mysql_conn.execute(text(f"SELECT id FROM {table_name}")).fetchall()
        mysql_ids = {row[0] for row in id_rows}
    except Exception:
        pass

    new_rows = [row for row in rows if row[0] not in mysql_ids]
    if not new_rows:
        print(f"  [SKIP] {table_name}: all {len(rows)} rows already exist in MySQL")
        return 0

    col_str = ", ".join(cols)
    placeholders = ", ".join([f":{c}" for c in cols])

    count = 0
    for row in new_rows:
        row_dict = dict(zip(cols, row))
        try:
            mysql_conn.execute(
                text(f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders})"),
                row_dict,
            )
            count += 1
        except Exception as exc:
            print(f"  [WARN] {table_name} id={row[0]}: {exc}")

    mysql_conn.commit()
    print(f"  [OK] {table_name}: {count} new rows migrated (skipped {len(rows) - count} existing/errors)")
    return count


def main():
    print(f"SQLite: {SQLITE_PATH}")
    safe_mysql = MYSQL_URI
    if "@" in safe_mysql:
        safe_mysql = safe_mysql.split("@")[1]
    print(f"MySQL:  {safe_mysql}")
    print()

    with sqlite_engine.connect() as sqlite_conn, mysql_engine.connect() as mysql_conn:
        # Show what's in SQLite
        print("=== SQLite summary ===")
        for t in TABLES:
            n = sqlite_row_count(sqlite_conn, t)
            if n >= 0:
                print(f"  {t}: {n} rows")
        print()

        # Disable FK checks for migration
        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        mysql_conn.commit()

        print("=== Migrating ===")
        total = 0
        for table in TABLES:
            total += migrate_table(table, sqlite_conn, mysql_conn)

        # Re-enable FK checks
        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        mysql_conn.commit()

    sqlite_engine.dispose()
    mysql_engine.dispose()

    print(f"\nDone. {total} total rows migrated to MySQL.")
    if total > 0:
        print("Restart the app to use the migrated data.")


if __name__ == "__main__":
    main()
