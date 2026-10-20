#!/usr/bin/env bash
# Screenshot every admin page of a running server at each width.
#   shots.sh --name <name> [--base http://127.0.0.1:PORT] [--brand B]
#            [--widths 1440,390] [--height 900] [--only a,b] [--no-video]
#            [--contact] [--out DIR]
# Without --base the port comes from the pid file serve.sh wrote. Output goes
# to <var>/run/<name>/<brand>/ unless --out says otherwise; a directory that
# is not an earlier run of the same name and brand is refused, not cleared.
# Exit status 1 when nothing answers, or when any page errored.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
    echo "usage: shots.sh --name <name> [--base URL] [--brand B] [--widths 1440,390] [--height 900] [--only a,b] [--no-video] [--contact] [--out DIR]" >&2
    exit 64
}

raw_name=""
base=""
brand=""
widths="1440,390"
height=900
only=""
video=1
contact=0
out=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --name) [ "$#" -ge 2 ] || usage; raw_name="$2"; shift 2 ;;
        --base) [ "$#" -ge 2 ] || usage; base="$2"; shift 2 ;;
        --brand) [ "$#" -ge 2 ] || usage; brand="$2"; shift 2 ;;
        --widths) [ "$#" -ge 2 ] || usage; widths="$2"; shift 2 ;;
        --height) [ "$#" -ge 2 ] || usage; height="$2"; shift 2 ;;
        --only) [ "$#" -ge 2 ] || usage; only="$2"; shift 2 ;;
        --out) [ "$#" -ge 2 ] || usage; out="$2"; shift 2 ;;
        --no-video) video=0; shift ;;
        --contact) contact=1; shift ;;
        *) usage ;;
    esac
done
[ -n "$raw_name" ] || usage
# The Python half runs from the checkout, so a relative --out is made absolute.
if [ -n "$out" ]; then
    mkdir -p "$out"
    out="$(cd "$out" && pwd -P)"
fi

name="$(harness_name "$raw_name")"
checkout="$(harness_checkout)"
var="$(harness_var)"
pidfile="$var/run/$name/pid"

pidfile_value() {
    sed -n "s/^$1=//p" "$pidfile" 2>/dev/null | head -n 1
}

if [ -z "$base" ]; then
    if [ ! -f "$pidfile" ]; then
        echo "shots.sh: nothing answers for '$name': no server is recorded; run serve.sh $name <port> or give --base" >&2
        exit 1
    fi
    base="http://127.0.0.1:$(pidfile_value port)"
    if [ -z "$brand" ]; then
        brand="$(pidfile_value brand)"
    fi
fi
base="${base%/}"
brand="${brand:-default}"
port="${base##*:}"
port="${port%%/*}"

status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$base/admin/login/" || true)"
if [ "$status" != "200" ]; then
    echo "shots.sh: nothing answers on port $port ($base/admin/login/ gave '${status:-no response}')" >&2
    exit 1
fi

# The pages come from the checkout's own admin site and the name's database.
harness_env "$name" "$brand"
(cd "$checkout" && "$HARNESS_PYTHON" -m harness pages "$name")

args=(--name "$name" --base "$base" --brand "$brand" --widths "$widths" --height "$height")
[ -z "$only" ] || args+=(--only "$only")
[ -z "$out" ] || args+=(--out "$out")
[ "$video" -eq 1 ] || args+=(--no-video)

status=0
(cd "$checkout" && "$HARNESS_PYTHON" -m harness.shots "${args[@]}") || status=$?

if [ "$contact" -eq 1 ]; then
    run_dir="${out:-$var/run/$name/$brand}"
    if [ -f "$run_dir/manifest.json" ]; then
        IFS=, read -r -a width_list <<<"$widths"
        for width in "${width_list[@]}"; do
            "$(dirname "${BASH_SOURCE[0]}")/contact.sh" "$run_dir" --width "$width"
        done
    fi
fi
exit "$status"
