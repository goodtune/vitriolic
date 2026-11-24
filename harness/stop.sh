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

if ! harness_is_runserver "$pid" "$port"; then
    rm -f "$pidfile"
    echo "stop.sh: '$name' is not running (pid ${pid:-unknown} is gone or is not its runserver)"
    exit 0
fi

# Any child of the server that is itself a runserver goes with it.
targets=("$pid")
while read -r child; do
    [ -n "$child" ] || continue
    if harness_is_runserver "$child" "$port"; then
        targets+=("$child")
    fi
done < <(pgrep -P "$pid" 2>/dev/null || true)

# True while any of the targets is still running.
any_alive() {
    local target
    for target in "${targets[@]}"; do
        if kill -0 "$target" 2>/dev/null; then
            return 0
        fi
    done
    return 1
}

kill "${targets[@]}" 2>/dev/null || true
for _ in $(seq 1 50); do
    any_alive || break
    sleep 0.2
done
if any_alive; then
    kill -9 "${targets[@]}" 2>/dev/null || true
    sleep 0.5
fi

if any_alive; then
    echo "stop.sh: '$name' is still running on port $port after kill -9; the pid file is kept" >&2
    exit 1
fi
rm -f "$pidfile"
echo "stop.sh: stopped '$name' (port $port)"
