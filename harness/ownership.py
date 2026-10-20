"""Whose database this is, for the Python entry points.

``db.sh`` records the checkout that made a database as a comment on it, and
``harness_db_check`` in ``lib.sh`` refuses to go on when the comment names
another checkout. ``python -m harness`` reads the database without going
through a script, so it makes the same comparison here.
"""

from pathlib import Path

from django.db import connection

#: The checkout this file belongs to, with symlinks resolved as ``pwd -P`` does.
CHECKOUT = Path(__file__).resolve().parents[1]


def recorded_owner() -> str:
    """The checkout recorded on the current database, or ``""`` for none."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        )
        row = cursor.fetchone()
    return (row[0] if row else "") or ""


def refusal(checkout: Path = CHECKOUT) -> str | None:
    """Why this checkout may not use the current database, or ``None``."""
    owner = recorded_owner()
    if owner == str(checkout):
        return None
    return (
        "harness: %s belongs to %s (this is %s); use db.sh --reset to take it over"
        % (
            connection.settings_dict["NAME"],
            owner or "nobody who left a name",
            checkout,
        )
    )
