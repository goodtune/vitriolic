#!/bin/bash
# Update vendored Jodit editor files.
#
# Usage: ./update-jodit.sh [version]
#   version: optional npm version specifier (default: latest)
#
# Current version: 4.12.2

set -euo pipefail

VERSION="${1:-latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKDIR="$(mktemp -d)"

trap 'rm -rf "$WORKDIR"' EXIT

echo "Downloading jodit@${VERSION}..."
(cd "$WORKDIR" && npm pack "jodit@${VERSION}" --silent)

echo "Extracting..."
tar xzf "$WORKDIR"/jodit-*.tgz -C "$WORKDIR"

echo "Copying es2021 dist files..."
cp "$WORKDIR/package/es2021/jodit.min.js" "$SCRIPT_DIR/js/jodit.min.js"
cp "$WORKDIR/package/es2021/jodit.min.css" "$SCRIPT_DIR/css/jodit.min.css"

# Show the version we installed
INSTALLED=$(grep -o 'Version: v[0-9.]*' "$SCRIPT_DIR/js/jodit.min.js" | head -1)
echo "Updated to ${INSTALLED}"
echo "Don't forget to update the version comment in this script."
