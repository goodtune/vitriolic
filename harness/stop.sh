#!/usr/bin/env bash
# Stop the dev server serve.sh started for a name.
#   stop.sh <name>
# Kills the recorded pid only while its command line still names runserver and
# the port. "Not running" is not an error.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ "$#" -ne 1 ]; then
    echo "usage: stop.sh <name>" >&2
    exit 64
fi

name="$(harness_name "$1")"
var="$(harness_var)"
pidfile="$var/run/$name/pid"

if [ ! -f "$pidfile" ]; then
    echo "stop.sh: '$name' is not running"
    exit 0
fi

pid="$(sed -n 's/^pid=//p' "$pidfile" | head -n 1)"
port="$(sed -n 's/^port=//p' "$pidfile" | head -n 1)"

command=""
if [ -n "$pid" ] && [ -n "$port" ]; then
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
fi
case "$command" in
    *runserver*"$port"*) ;;
    *)
        rm -f "$pidfile"
        echo "stop.sh: '$name' is not running (pid ${pid:-unknown} is gone or is not its runserver)"
        exit 0
        ;;
esac

# Any child of the server that is itself a runserver goes with it.
targets=("$pid")
while read -r child; do
    [ -n "$child" ] || continue
    case "$(ps -p "$child" -o command= 2>/dev/null || true)" in
        *runserver*"$port"*) targets+=("$child") ;;
    esac
done < <(pgrep -P "$pid" 2>/dev/null || true)

kill "${targets[@]}" 2>/dev/null || true
for _ in $(seq 1 50); do
    alive=0
    for target in "${targets[@]}"; do
        if kill -0 "$target" 2>/dev/null; then
            alive=1
        fi
    done
    [ "$alive" -eq 1 ] || break
    sleep 0.2
done
if [ "$alive" -eq 1 ]; then
    kill -9 "${targets[@]}" 2>/dev/null || true
fi

rm -f "$pidfile"
echo "stop.sh: stopped '$name' (port $port)"
