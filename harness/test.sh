#!/usr/bin/env bash
# Run the project's tests against the harness PostgreSQL, with no Docker.
#   test.sh <name> [unit|e2e] [--] [test labels or pytest arguments...]
# unit (the default) runs the Django test suite through tox, environment
# dj61-py314; e2e runs the Playwright suite through the e2e environment with
# the in-memory commentary backend. The harness database for <name> must exist
# and belong to this checkout (db.sh); Django makes its own
# test_vitriolic_<name> database beside it.
# Set PLAYWRIGHT_CHROMIUM_EXECUTABLE to use a browser that is already installed.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
    echo "usage: test.sh <name> [unit|e2e] [--] [arguments...]" >&2
    exit 64
}

[ "$#" -ge 1 ] || usage
name="$1"
shift

mode=unit
case "${1-}" in
    unit | e2e)
        mode="$1"
        shift
        ;;
esac
if [ "${1-}" = "--" ]; then
    shift
fi

harness_env "$name"
harness_db_check "$name"
checkout="$(harness_checkout)"

cd "$checkout"
case "$mode" in
    unit)
        exec tox -e dj61-py314 \
            --override testenv.docker= \
            --override testenv.passenv=DATABASE_URL,DB_5432_TCP_PORT \
            -- "$@"
        ;;
    e2e)
        # The e2e environment declares its own docker and setenv, so the
        # overrides name it; its setenv is replaced to drop the Redis backend.
        COMPOPS_EVENTS_BACKEND=memory exec tox -e e2e \
            --override testenv:e2e.docker= \
            --override testenv:e2e.passenv=DATABASE_URL,DB_5432_TCP_PORT,COMPOPS_EVENTS_BACKEND,PLAYWRIGHT_CHROMIUM_EXECUTABLE \
            --override 'testenv:e2e.setenv=DJANGO_ALLOW_ASYNC_UNSAFE=1' \
            -- "$@"
        ;;
esac
