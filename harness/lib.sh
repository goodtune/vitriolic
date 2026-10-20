# Shared by the harness scripts: source it from bash, do not run it. It reads
# BASH_SOURCE to find its checkout, so zsh and sh cannot source it; from another
# shell, run the work inside bash -c '...'.
#
# Everything a name owns lives under the state root, in
# {media,log,run,state}/<name>, and in the database vitriolic_<name>.
# harness/paths.py computes the same locations for the Python modules.

PGBIN="${VITRIOLIC_PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
PGPORT_HARNESS="${VITRIOLIC_PG_PORT:-55432}"
PGUSER_HARNESS="${VITRIOLIC_PG_USER:-vitriolic}"

# The absolute path of the checkout that owns this harness/ directory.
harness_checkout() {
    (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
}

# The state root, created on demand.
harness_var() {
    local var="${VITRIOLIC_HARNESS_VAR:-${XDG_STATE_HOME:-$HOME/.local/state}/vitriolic-harness}"
    mkdir -p "$var"
    printf '%s\n' "$var"
}

# Lower-case a name to [a-z0-9_]. Exit status 2 when nothing is left.
harness_name() {
    local name
    name="$(printf '%s' "${1-}" | LC_ALL=C tr 'A-Z' 'a-z' | LC_ALL=C tr -c 'a-z0-9_' '_')"
    name="${name#"${name%%[!_]*}"}"
    name="${name%"${name##*[!_]}"}"
    if [ -z "$name" ]; then
        echo "harness: the name '${1-}' is empty once normalised to [a-z0-9_]" >&2
        return 2
    fi
    printf '%s\n' "$name"
}

# Export the environment the demo project runs in for this name.
#   harness_env <name> [brand] [htmx]
harness_env() {
    local name checkout var
    name="$(harness_name "${1-}")" || return 2
    local brand="${2:-${ADMIN_BRAND:-default}}"
    local htmx="${3:-${HTMX_ADMIN_TABS:-0}}"
    checkout="$(harness_checkout)"
    var="$(harness_var)"
    mkdir -p "$var/media/$name" "$var/log/$name" "$var/run/$name" "$var/state/$name"

    export HARNESS_PYTHON="${HARNESS_PYTHON:-$checkout/.venv/bin/python}"
    export DJANGO_SETTINGS_MODULE=vitriolic.settings
    export PYTHONPATH="$checkout/tests"
    export DATABASE_URL="psql://$PGUSER_HARNESS@localhost:$PGPORT_HARNESS/vitriolic_$name"
    export DB_5432_TCP_PORT="$PGPORT_HARNESS"
    export DJANGO_DB_WAIT=0
    export MEDIA_ROOT="$var/media/$name"
    export COMPOPS_EVENTS_BACKEND=memory
    export ADMIN_BRAND="$brand"
    export HTMX_ADMIN_TABS="$htmx"
    export PYTHONUNBUFFERED=1
    # A dummy so the cloudinary library can build image URLs while pages
    # render; nothing is ever uploaded.
    export CLOUDINARY_URL="${CLOUDINARY_URL:-cloudinary://harness:harness@harness}"
    # The footer shows a host name; an invented one keeps the machine's own
    # name out of pictures made for a public record.
    export VITRIOLIC_DEMO_HOSTNAME="${VITRIOLIC_DEMO_HOSTNAME:-demo.example}"
}

# True when the process is a runserver listening on exactly 127.0.0.1:<port>
# (the address is the first argument after runserver, as serve.sh passes it).
#   harness_is_runserver <pid> <port>
harness_is_runserver() {
    local pid="${1-}" port="${2-}" command
    [ -n "$pid" ] && [ -n "$port" ] || return 1
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return 1
    case "$command " in
        *" runserver 127.0.0.1:$port "*) return 0 ;;
        *) return 1 ;;
    esac
}

# Exit status 3, naming the owner, unless the database for <name> was made by
# this checkout (db.sh records the owner as a comment on the database). Exit
# status 1 when PostgreSQL does not answer or the database does not exist.
# Silent when the database is ours.
#   harness_db_check <name>
harness_db_check() {
    local name database checkout owner exists
    name="$(harness_name "${1-}")" || return 2
    database="vitriolic_$name"
    checkout="$(harness_checkout)"
    if ! "$PGBIN/pg_isready" -q -h 127.0.0.1 -p "$PGPORT_HARNESS"; then
        echo "harness: nothing answers on port $PGPORT_HARNESS; run pg.sh start" >&2
        return 1
    fi
    exists="$("$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT_HARNESS" -U "$PGUSER_HARNESS" -X -q -t -A -d postgres \
        -c "SELECT 1 FROM pg_database WHERE datname = '$database'")" || return 1
    if [ -z "$exists" ]; then
        echo "harness: the database $database does not exist; run db.sh $name" >&2
        return 1
    fi
    owner="$("$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT_HARNESS" -U "$PGUSER_HARNESS" -X -q -t -A -d postgres \
        -c "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = '$database'")" || return 1
    if [ "$owner" != "$checkout" ]; then
        echo "harness: $database belongs to ${owner:-nobody who left a name} (this is $checkout); use db.sh --reset $name to take it over" >&2
        return 3
    fi
}
