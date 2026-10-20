#!/usr/bin/env bash
# Run the demo project's dev server for a name, in a chosen brand.
#   serve.sh <name> <port> [--brand default|forest|sherbet] [--htmx-tabs]
# Exit status 1 when the port is taken, the name already has a server, or the
# server does not answer within 30 seconds.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
    echo "usage: serve.sh <name> <port> [--brand default|forest|sherbet] [--htmx-tabs]" >&2
    exit 64
}

if [ "$#" -lt 2 ]; then
    usage
fi
raw_name="$1"
port="$2"
shift 2

brand=default
htmx=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --brand)
            [ "$#" -ge 2 ] || usage
            brand="$2"
            shift 2
            ;;
        --htmx-tabs)
            htmx=1
            shift
            ;;
        *) usage ;;
    esac
done

case "$brand" in
    default | forest | sherbet) ;;
    *)
        echo "serve.sh: unknown brand '$brand' (default, forest or sherbet)" >&2
        exit 64
        ;;
esac
case "$port" in
    '' | *[!0-9]*)
        echo "serve.sh: the port '$port' is not a number" >&2
        exit 64
        ;;
esac

name="$(harness_name "$raw_name")"
checkout="$(harness_checkout)"
var="$(harness_var)"
pidfile="$var/run/$name/pid"
logfile="$var/log/$name/server.log"
url="http://127.0.0.1:$port/admin/"

# The value of a key in the pid file, or nothing.
pidfile_value() {
    sed -n "s/^$1=//p" "$pidfile" 2>/dev/null | head -n 1
}

# True when the pid is alive and is still a runserver on this port.
is_our_server() {
    local pid="$1" listen="$2" command
    [ -n "$pid" ] || return 1
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return 1
    case "$command" in
        *runserver*"$listen"*) return 0 ;;
        *) return 1 ;;
    esac
}

if [ -f "$pidfile" ]; then
    old_pid="$(pidfile_value pid)"
    old_port="$(pidfile_value port)"
    if is_our_server "$old_pid" "${old_port:-0}"; then
        echo "serve.sh: '$name' is already serving on port $old_port (pid $old_pid); run stop.sh $name first" >&2
        exit 1
    fi
    rm -f "$pidfile"
fi

if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "serve.sh: something already answers on port $port" >&2
    exit 1
fi

harness_env "$name" "$brand" "$htmx"
: >"$logfile"

nohup "$HARNESS_PYTHON" "$checkout/tests/manage.py" runserver "127.0.0.1:$port" --noreload \
    >>"$logfile" 2>&1 </dev/null &
pid=$!

{
    echo "pid=$pid"
    echo "port=$port"
    echo "brand=$brand"
    echo "htmx_tabs=$htmx"
    echo "checkout=$checkout"
} >"$pidfile"

for _ in $(seq 1 60); do
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "serve.sh: the server for '$name' exited early; last of $logfile:" >&2
        tail -n 20 "$logfile" >&2
        rm -f "$pidfile"
        exit 1
    fi
    status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$port/admin/login/" || true)"
    if [ "$status" = "200" ]; then
        echo "$url"
        exit 0
    fi
    sleep 0.5
done

echo "serve.sh: no 200 from ${url}login/ within 30 seconds; last of $logfile:" >&2
tail -n 20 "$logfile" >&2
"$(dirname "${BASH_SOURCE[0]}")/stop.sh" "$name" >/dev/null || true
exit 1
