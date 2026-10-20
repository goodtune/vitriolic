#!/usr/bin/env bash
# Run the demo project's manage.py against a name's database.
#   manage.sh <name> <args...>
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ "$#" -lt 2 ]; then
    echo "usage: manage.sh <name> <manage.py args...>" >&2
    exit 64
fi

name="$1"
shift
harness_env "$name"
exec "$HARNESS_PYTHON" "$(harness_checkout)/tests/manage.py" "$@"
