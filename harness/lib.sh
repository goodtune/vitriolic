# Shared by the harness scripts: source it, do not run it.
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
}
