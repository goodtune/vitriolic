#!/usr/bin/env bash
# Tile a run's screenshots at one width into one contact sheet.
#   contact.sh <run-dir> [--width 1440] [--columns 4] [--tile-width 360] [--out contact-<width>.png]
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ "$#" -lt 1 ]; then
    echo "usage: contact.sh <run-dir> [--width 1440] [--columns 4] [--tile-width 360] [--out FILE]" >&2
    exit 64
fi

checkout="$(harness_checkout)"
python="${HARNESS_PYTHON:-$checkout/.venv/bin/python}"
PYTHONPATH="$checkout" exec "$python" -m harness.contact "$@"
