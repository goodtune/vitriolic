#!/usr/bin/env bash
# A temporary PostgreSQL cluster for the harness: no service, no brew.
#   pg.sh start|stop|status|psql [<name>] [args]
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

host=127.0.0.1
port="$PGPORT_HARNESS"
user="$PGUSER_HARNESS"
var="$(harness_var)"
data="$var/pg"
mkdir -p "$var/log"

answering() {
    "$PGBIN/pg_isready" -h "$host" -p "$port"
}

ours_running() {
    [ -f "$data/PG_VERSION" ] && "$PGBIN/pg_ctl" -D "$data" status >/dev/null 2>&1
}

cmd="${1:-}"
[ "$#" -gt 0 ] && shift

case "$cmd" in
start)
    if answering; then
        echo "pg.sh: nothing to start, something already answers on port $port" >&2
        exit 0
    fi
    if [ ! -f "$data/PG_VERSION" ]; then
        "$PGBIN/initdb" -D "$data" -U "$user" --auth=trust >"$var/log/pg-initdb.log"
    fi
    "$PGBIN/pg_ctl" -D "$data" -w -l "$var/log/pg.log" \
        -o "-p $port -k /tmp -c listen_addresses=$host" start >/dev/null
    answering
    ;;
stop)
    if ours_running; then
        "$PGBIN/pg_ctl" -D "$data" -w stop >/dev/null
        echo "pg.sh: stopped the cluster in $data" >&2
    else
        echo "pg.sh: the harness cluster in $data is not running; leaving anything else alone" >&2
    fi
    ;;
status)
    if ours_running; then
        echo "pg.sh: the harness cluster in $data is running" >&2
    fi
    answering
    ;;
psql)
    if [ "$#" -gt 0 ] && [[ "$1" != -* ]]; then
        dbname="vitriolic_$(harness_name "$1")"
        shift
    else
        dbname=postgres
    fi
    exec "$PGBIN/psql" -h "$host" -p "$port" -U "$user" "$dbname" "$@"
    ;;
*)
    echo "usage: pg.sh start|stop|status|psql [<name>] [args]" >&2
    exit 64
    ;;
esac
