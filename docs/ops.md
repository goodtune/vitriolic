# Tournament Ops

`tournamentcontrol.competition.ops` is a mountable site for running a
tournament day: a results and live-stream dashboard for the ops desk and a
commentary booth per streamed ground. Pages update live over Server-Sent
Events using [Datastar](https://data-star.dev) (vendored, 1.0.4); the
rest of the admin is untouched.

## Mounting

```python
# urls.py
from tournamentcontrol.competition.ops.sites import OpsSite

urlpatterns += [path("ops/", OpsSite().urls)]
```

Install the extra: `pip install vitriolic[ops]` (adds `datastar-py` and
`redis`). Nothing happens unless the site is mounted.

The booth refuses an action with a normal 200 response that carries the
reason in the lamp. Datastar drops the body of non-200 responses, so a
refusal that used an error status would never reach the page.

## Who can do what

| Page or action | Needs |
| --- | --- |
| Ops dashboard pages | login and `is_staff` |
| Enter or edit a result | `competition.change_match` on the match (guardian object or global) |
| Enter scorers | `competition.add_simplescorematchstatistic` and `change_simplescorematchstatistic` |
| Start, test or stop a broadcast; whole-slot actions | `competition.stream_season` on the season |
| The booth | login and `competition.stream_season` on the season; staff status is not needed |

Grant a commentator pair one object permission on the season:

```python
from guardian.shortcuts import assign_perm
assign_perm("competition.stream_season", user, season)
```

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `OPS_EVENTS_BACKEND` | `"memory"` | `"memory"` works for one server process only; use `"redis"` with more than one worker |
| `OPS_EVENTS_REDIS_URL` | `None` | required with the Redis backend |
| `OPS_EVENTS_KEEPALIVE` | `20` | seconds between SSE keep-alive comments |
| `OPS_ACTIVITY_LENGTH` | `50` | events kept for the activity feed |

## Serving

The two `events/` endpoints are async streaming views and need an ASGI
server. granian 2.8.3 or later:

```
granian --interface asgi --workers 2 --http auto myproject.asgi:application
```

`manage.py runserver` is WSGI and cannot serve the streams; for local
work use `granian --reload --interface asgi` or `uvicorn --reload`.

Behind nginx, disable buffering for the stream locations (the responses
also send `X-Accel-Buffering: no`) and set `proxy_read_timeout` above the
keep-alive interval. Serve HTTP/2 to browsers so one person can keep the
ops page and two booths open. Do not put `GZipMiddleware` in front of the
streams.

The `events/` endpoints log and keep streaming when a single push fails to
render. They also validate their database connection around each push.

## Broadcast status

`Match.live_stream_status` and `LiveStreamEvent.live_stream_status`
record YouTube's lifecycle status after every transition made from the
site. Both columns are 20 characters wide and store YouTube's
`lifeCycleStatus` values, including the transient `liveStarting` and
`testStarting`. The site writes the status without model signals, so a
stream transition does not recalculate ladders.

Changes made in YouTube Studio are picked up by the Celery task
`tournamentcontrol.competition.tasks.refresh_all_live_stream_status`;
schedule it every minute:

```python
CELERY_BEAT_SCHEDULE = {
    "refresh-live-stream-status": {
        "task": "tournamentcontrol.competition.tasks.refresh_all_live_stream_status",
        "schedule": 60.0,
    },
}
```

The refresh task isolates each season, so one season's expired credentials
do not stop the others.

## Tests

Unit tests are plain django-test-plus `TestCase` classes; the SSE views
are tested with `async def` methods and `self.async_client`. The e2e
tests run under a uvicorn server started in the test process
(`asgi_live_server` in `tests/e2e/conftest.py`) because the WSGI
`live_server` cannot serve an endless stream. The fixture bounds uvicorn's
shutdown with a one second graceful timeout. The e2e tox environment
runs Redis in docker and uses the Redis backend. `tox -e e2e` declares its
containers with one `docker = db` entry and one `docker = redis` entry,
one per line.
