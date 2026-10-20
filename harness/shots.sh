#!/usr/bin/env bash
# Screenshot every admin page of a running server at each width, record the
# flow, and take the flow's rows out of the database again.
#   shots.sh --name <name> [--base http://127.0.0.1:PORT] [--brand B]
#            [--htmx-tabs] [--widths 1440,390] [--height 900] [--only a,b]
#            [--no-video] [--contact] [--out DIR]
# The server's pid file, which serve.sh wrote, is the authority for the brand
# and for whether tabs load over HTMX: a --brand that disagrees with it is
# refused (exit status 64). With --base and no pid file for that server,
# --brand is required, and --htmx-tabs says how the server was started.
# Output goes to <var>/run/<name>/<brand>/ (<brand>-htmx/ for HTMX tabs)
# unless --out says otherwise; a directory that is not an earlier run of the
# same name, brand and tab mode is refused, not cleared. The directory is
# cleared before anything else, so a run that fails early leaves only its
# manifest, which says why.
# Exit status 1 when nothing answers, or when any page or step errored, or a
# set of pictures is incomplete; 3 when another checkout owns the database.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
    echo "usage: shots.sh --name <name> [--base URL] [--brand B] [--htmx-tabs] [--widths 1440,390] [--height 900] [--only a,b] [--no-video] [--contact] [--out DIR]" >&2
    exit 64
}

raw_name=""
base=""
brand=""
htmx_flag=""
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
        --htmx-tabs) htmx_flag=1; shift ;;
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
harness_env "$name"
harness_db_check "$name"

pidfile_value() {
    sed -n "s/^$1=//p" "$pidfile" 2>/dev/null | head -n 1
}

base_given=0
no_server=""
if [ -n "$base" ]; then
    base_given=1
elif [ -f "$pidfile" ]; then
    base="http://127.0.0.1:$(pidfile_value port)"
else
    no_server="nothing answers for '$name': no server is recorded; run serve.sh $name <port> or give --base"
    # Without a server there is no base and no pid file to say which brand and
    # which directory this run is for, unless --brand does.
    if [ -z "$brand" ]; then
        echo "shots.sh: $no_server" >&2
        exit 1
    fi
    base="http://127.0.0.1:0"
fi
base="${base%/}"
port="${base##*:}"
port="${port%%/*}"

# The pid file describes the server on its port; --base may point elsewhere.
recorded=0
if [ -f "$pidfile" ] && { [ "$base_given" -eq 0 ] || [ "$(pidfile_value port)" = "$port" ]; }; then
    recorded=1
fi
if [ "$recorded" -eq 1 ]; then
    server_brand="$(pidfile_value brand)"
    server_htmx="$(pidfile_value htmx_tabs)"
    server_htmx="${server_htmx:-0}"
    if [ -n "$brand" ] && [ "$brand" != "$server_brand" ]; then
        echo "shots.sh: --brand $brand disagrees with the server on port $port, which was started with brand '$server_brand' (pid file $pidfile)" >&2
        exit 64
    fi
    if [ -n "$htmx_flag" ] && [ "$server_htmx" != "1" ]; then
        echo "shots.sh: --htmx-tabs disagrees with the server on port $port, which was started with htmx_tabs=$server_htmx (pid file $pidfile)" >&2
        exit 64
    fi
    brand="$server_brand"
    htmx="$server_htmx"
else
    if [ -z "$brand" ]; then
        echo "shots.sh: --base with no pid file for that server needs --brand (default, forest or sherbet)" >&2
        exit 64
    fi
    htmx="${htmx_flag:-0}"
fi
case "$brand" in
    '' | *[!a-z0-9_-]*)
        echo "shots.sh: the brand '$brand' is not a brand name" >&2
        exit 64
        ;;
esac

suffix=""
if [ "$htmx" = "1" ]; then
    suffix="-htmx"
fi
run_dir="${out:-$var/run/$name/$brand$suffix}"

# The pages come from the checkout's own admin site and the name's database.
harness_env "$name" "$brand" "$htmx"

shots=("$HARNESS_PYTHON" -m harness.shots --name "$name" --base "$base" --brand "$brand"
    --widths "$widths" --height "$height" --out "$run_dir")
[ -z "$only" ] || shots+=(--only "$only")
[ "$video" -eq 1 ] || shots+=(--no-video)
[ "$htmx" != "1" ] || shots+=(--htmx-tabs)

# Clear the run directory first, so that no failure below can leave the
# pictures of an earlier run looking like this one's.
(cd "$checkout" && "${shots[@]}" --prepare)

fail_run() {
    (cd "$checkout" && "${shots[@]}" --fail "$1") || true
    exit 1
}

if [ -n "$no_server" ]; then
    echo "shots.sh: $no_server" >&2
    fail_run "$no_server"
fi

status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$base/admin/login/" || true)"
if [ "$status" != "200" ]; then
    echo "shots.sh: nothing answers on port $port ($base/admin/login/ gave '${status:-no response}')" >&2
    fail_run "nothing answers on port $port ($base/admin/login/ gave '${status:-no response}')"
fi

if ! (cd "$checkout" && "$HARNESS_PYTHON" -m harness pages "$name"); then
    echo "shots.sh: page discovery failed" >&2
    fail_run "page discovery failed"
fi

status=0
(cd "$checkout" && "${shots[@]}") || status=$?

# The flow adds rows to the database; take them out again, by the stamp the
# flow put on them at each width, so the next run captures the seed alone.
if [ "$video" -eq 1 ] && [ -f "$run_dir/manifest.json" ]; then
    stamps="$("$HARNESS_PYTHON" -c '
import json, sys
for width, stamp in json.load(open(sys.argv[1])).get("flow_stamps", {}).items():
    print(stamp)
' "$run_dir/manifest.json")"
    for stamp in $stamps; do
        (cd "$checkout" && "$HARNESS_PYTHON" -m harness unflow "$stamp") || {
            echo "shots.sh: could not remove the rows of flow $stamp; run python -m harness unflow $stamp" >&2
            status=1
        }
    done
fi

if [ "$contact" -eq 1 ] && [ -f "$run_dir/manifest.json" ]; then
    IFS=, read -r -a width_list <<<"$widths"
    for width in "${width_list[@]}"; do
        # A contact sheet that fails is reported, and never changes the status.
        "$(dirname "${BASH_SOURCE[0]}")/contact.sh" "$run_dir" --width "$width" ||
            echo "shots.sh: no contact sheet at width $width" >&2
    done
fi
exit "$status"
