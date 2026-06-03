import os
from typing import Mapping, Optional


MYSQL_DIALECTS = {"mysql", "mariadb"}
TRUTHY_VALUES = {"1", "true", "yes", "on"}


def allows_schema_bootstrap(
    dialect_name: Optional[str],
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """Only MySQL needs an explicit opt-in before creating a missing schema."""
    normalized_dialect = (dialect_name or "").strip().lower()
    if normalized_dialect not in MYSQL_DIALECTS:
        return True

    source = env if env is not None else os.environ
    flag = (source.get("ALLOW_MYSQL_SCHEMA_BOOTSTRAP", "") or "").strip().lower()
    return flag in TRUTHY_VALUES


def schema_bootstrap_blocked_message() -> str:
    return (
        "Refusing to auto-create missing MySQL tables. "
        "Check that the app is connected to the intended database, restore the "
        "schema/data if needed, or set ALLOW_MYSQL_SCHEMA_BOOTSTRAP=true only "
        "for a confirmed empty development database."
    )
