#!/bin/bash
# Update the vendored Signature Pad (https://github.com/szimek/signature_pad),
# which draws the signature of a SignatureField.
#
# Usage: ./update-signature-pad.sh [version]
#   version: optional npm version specifier (default: latest)
#
# Current version: 5.1.5

set -euo pipefail

VERSION="${1:-latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKDIR="$(mktemp -d)"

trap 'rm -rf "$WORKDIR"' EXIT

echo "Downloading signature_pad@${VERSION}..."
(cd "$WORKDIR" && npm pack "signature_pad@${VERSION}" --silent)

echo "Extracting..."
tar xzf "$WORKDIR"/signature_pad-*.tgz -C "$WORKDIR"

# The source map is not shipped, so the comment that names it goes: a browser
# with its developer tools open would ask for it and log a 404.
echo "Copying the UMD build..."
grep -v '^//# sourceMappingURL=' "$WORKDIR/package/dist/signature_pad.umd.min.js" \
	> "$SCRIPT_DIR/js/signature_pad.umd.min.js"

INSTALLED=$(grep -o 'Signature Pad v[0-9.]*' "$SCRIPT_DIR/js/signature_pad.umd.min.js" | head -1)
echo "Updated to ${INSTALLED}"
echo "Don't forget to update the version comment in this script."
