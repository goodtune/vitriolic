#!/usr/bin/env bash
# Migrate a name's database and seed it with the invented association.
#   seed.sh <name>
# Safe to run again: it migrates and then adds only what is missing.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ "$#" -ne 1 ]; then
    echo "usage: seed.sh <name>" >&2
    exit 64
fi

name="$1"
checkout="$(harness_checkout)"
"$checkout/harness/manage.sh" "$name" migrate --noinput

harness_env "$name"
cd "$checkout"
exec "$HARNESS_PYTHON" -m harness seed
