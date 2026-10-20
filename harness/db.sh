#!/usr/bin/env bash
# One database per name, owned by the checkout that created it.
#   db.sh [--reset] <name>
# Exit status 3 when the database belongs to another checkout.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

reset=0
if [ "${1-}" = "--reset" ]; then
    reset=1
    shift
fi
if [ "$#" -ne 1 ]; then
    echo "usage: db.sh [--reset] <name>" >&2
    exit 64
fi

name="$(harness_name "$1")"
checkout="$(harness_checkout)"
var="$(harness_var)"
database="vitriolic_$name"
conn=(-h 127.0.0.1 -p "$PGPORT_HARNESS" -U "$PGUSER_HARNESS")

sql() {
    "$PGBIN/psql" "${conn[@]}" -X -q -t -A -v ON_ERROR_STOP=1 "$@"
}

exists="$(sql -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$database'")"

if [ -n "$exists" ] && [ "$reset" -eq 0 ]; then
    owner="$(sql -d postgres -c "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = '$database'")"
    if [ "$owner" = "$checkout" ]; then
        echo "db.sh: $database is already yours" >&2
        harness_env "$name"
        echo "$DATABASE_URL"
        exit 0
    fi
    echo "db.sh: $database belongs to ${owner:-nobody who left a name} (this is $checkout); use --reset to take it over" >&2
    exit 3
fi

if [ "$reset" -eq 1 ]; then
    # Removing the run directory would lose the pid file of a live server.
    pidfile="$var/run/$name/pid"
    if [ -f "$pidfile" ]; then
        live_pid="$(sed -n 's/^pid=//p' "$pidfile" | head -n 1)"
        live_port="$(sed -n 's/^port=//p' "$pidfile" | head -n 1)"
        if harness_is_runserver "$live_pid" "$live_port"; then
            echo "db.sh: '$name' is serving on port $live_port; run stop.sh $name first" >&2
            exit 1
        fi
    fi
    if [ -n "$exists" ]; then
        "$PGBIN/dropdb" "${conn[@]}" --force "$database"
    fi
    rm -rf "${var:?}/media/$name" "${var:?}/state/$name" "${var:?}/run/$name"
fi

"$PGBIN/createdb" "${conn[@]}" "$database"
# A database with no owner would be refused by every script, so one whose owner
# could not be recorded is dropped again.
if ! printf 'COMMENT ON DATABASE "%s" IS :'"'"'owner'"'"';\n' "$database" |
    sql -d postgres -v owner="$checkout"; then
    "$PGBIN/dropdb" "${conn[@]}" --force "$database" || true
    echo "db.sh: could not record the owner of $database; dropped it" >&2
    exit 1
fi

harness_env "$name"
echo "db.sh: created $database for $checkout" >&2
echo "$DATABASE_URL"
