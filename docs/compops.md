# Tournament Ops

`tournamentcontrol.competition.compops` is a mountable site for running a
tournament day: a results and live-stream dashboard for the ops desk and a
commentary booth per streamed ground. Pages update live over Server-Sent
Events using [Datastar](https://data-star.dev) (vendored, 1.0.4); the
rest of the admin is untouched.

## Mounting

```python
# urls.py
from tournamentcontrol.competition.compops.sites import CompOpsSite

urlpatterns += [path("compops/", CompOpsSite().urls)]
```

Install the extra: `pip install vitriolic[async]` (adds `datastar-py` and
`redis`). Nothing happens unless the site is mounted.

Add `"touchtechnology.common.middleware.DatastarMiddleware"` to
`MIDDLEWARE`; it sets `request.datastar`, and `CompOpsSite()` raises
`ImproperlyConfigured` without it.

The templates use template partials (`{% partialdef %}` and `{% partial %}`)
without `{% load %}`, and the views render a partial by name, for example
`day.html#results`. Django 6.0 and later have partials built in and need no
settings. Django 5.2 needs three settings, set out in
[Template partials on Django 5.2](#template-partials-on-django-52).

The booth refuses an action with a normal 200 response that carries the
reason in the lamp. Datastar drops the body of non-200 responses, so a
refusal that used an error status would never reach the page. The lamp, like
a ground's block in the day page's streams column and a result row with an
open Edit or a refused save, is then held: the snapshot a reconnect sends
passes over it, and the next action, or a push about the same ground or
match, releases it. The template comment above `match_row` in `day.html`
explains the mechanism.

## Template partials on Django 5.2

Skip this section on Django 6.0 and later.

On Django 5.2 the partials come from
[django-template-partials](https://pypi.org/project/django-template-partials/)
25.3 or later. Install it yourself. A dependency cannot be limited to one
Django version, so the `async` extra leaves it out.

Three settings go together, and each fails in its own way when it is missing:

| Setting | When it is missing |
| --- | --- |
| `"template_partials"` in `INSTALLED_APPS` | `CompOpsSite()` raises `ImproperlyConfigured` when the URLconf loads |
| `"template_partials.templatetags.partials"` in the `builtins` of the template `OPTIONS` | the pages fail with `TemplateSyntaxError`: `Invalid block tag ... 'partialdef'` |
| the template loaders wrapped in `template_partials.loader.Loader` | the live updates fail with `TemplateDoesNotExist`, as they render a partial by name |

### A project that sets no loaders

This is the usual case, with `APP_DIRS` or without it. Add the app and the
builtins:

```python
INSTALLED_APPS = [
    # ...
    "template_partials",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "builtins": ["template_partials.templatetags.partials"],
            "context_processors": [
                # ...
            ],
        },
    },
]
```

Nothing else is needed. When Django starts, the app removes `APP_DIRS` and
puts the filesystem and app directories loaders, inside a cached loader,
inside its own loader. It finds the engine by its name, which for
`DjangoTemplates` is `django`. An entry with a different `NAME` is left alone:
wrap its loaders as in the next section.

### A project with its own loaders

The app replaces `loaders` that are not wrapped yet. It does this without a
message, and it uses its own list, so a loader of yours is gone and its
templates are not found. Wrap your loaders yourself, before you add the app:

```python
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "OPTIONS": {
            "builtins": ["template_partials.templatetags.partials"],
            "context_processors": [
                # ...
            ],
            "loaders": [
                (
                    "template_partials.loader.Loader",
                    [
                        (
                            "django.template.loaders.cached.Loader",
                            [
                                "myproject.loaders.TenantLoader",
                                "django.template.loaders.filesystem.Loader",
                                "django.template.loaders.app_directories.Loader",
                            ],
                        ),
                    ],
                ),
            ],
        },
    },
]
```

The app sees that the first loader is its own and leaves the list as it is.
These rules are easy to break:

- The `template_partials.loader.Loader` entry must be the first loader, and it
  must be a tuple (or list) of the loader and the loaders it wraps. A cached
  loader around it, or a plain string, does not work.
- Put all your loaders inside it, including the cached loader if you use one.
  A loader outside it never sees the `#name` of a partial.
- Remove `APP_DIRS`. Django does not accept `APP_DIRS` and `loaders` together.
  Add `"django.template.loaders.app_directories.Loader"` to the list instead.

### Checks

When the URLconf mounts `CompOpsSite`, `manage.py check` reports a missing
setting with the lines to add: `tournamentcontrol.competition.E002` for the
builtins and `E003` for the loaders. The app needs no check, as `CompOpsSite()`
refuses to mount without it. The check reports nothing on Django 6.0 and later,
and nothing when the site is not mounted.

It finds the site by its app name, `compops`. A site that you mount under
another `app_name`, or from a content node (a database row), is not seen. To
turn a check off, put its id in `SILENCED_SYSTEM_CHECKS`.

## Who can do what

| Page or action | Needs |
| --- | --- |
| Ops dashboard pages | login and `is_staff` |
| Enter or edit a result | `is_staff` and `competition.change_match` on the match (guardian object or global) |
| Enter scorers | `is_staff`, `competition.add_simplescorematchstatistic` and `change_simplescorematchstatistic` |
| Start, test or stop a broadcast; whole-slot actions | `is_staff` and `competition.stream_season` on the season |
| The booth | login and `competition.stream_season` on the season; staff status is not needed |

Every dashboard action is part of the dashboard, so it needs `is_staff`
as well as its own permission. Only the booth works without staff status.

Grant a commentator pair one object permission on the season:

```python
from guardian.shortcuts import assign_perm

assign_perm("competition.stream_season", user, season)
```

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `COMPOPS_EVENTS_BACKEND` | `"tournamentcontrol.competition.compops.events.memory.MemoryBackend"` | dotted path to the event bus class; the memory backend works for one server process only, so use `"tournamentcontrol.competition.compops.events.redis.RedisBackend"` with more than one worker or with the Celery refresh task |
| `COMPOPS_EVENTS_OPTIONS` | `{}` | keyword arguments for the backend class; the Redis backend needs `{"url": "redis://localhost:6379/0"}` |
| `COMPOPS_EVENTS_KEEPALIVE` | `20` | seconds between SSE keep-alive comments |
| `COMPOPS_ACTIVITY_LENGTH` | `50` | events kept for the activity feed |

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

## Tenants

On a [django-tenant-schemas](https://pypi.org/project/django-tenant-schemas/)
site, one event bus serves all the tenants. Each tenant has its own tables,
so two tenants can have a season with the same id. The bus keeps the events
of each tenant apart: it names the channel of a season from the schema that
the database connection points at. For season 3, the Redis backend uses
these names:

| Site | Channel | Recent events |
| --- | --- | --- |
| The tenant with the schema `alpha` | `compops:alpha:season:3` | `compops:alpha:season:3:recent` |
| A single-tenant site | `compops:season:3` | `compops:season:3:recent` |

An event goes to the tenant whose schema the connection points at when the
event is published. A request to the site of a tenant points the connection
at the schema of that tenant. Outside a request, use `tenant_context`, or a
Celery task that runs in the schema of the tenant. An event that is published
in the public schema goes to the public schema only, and no tenant's page
shows it.

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

The task checks each season with `live_stream=True` that has matches
dated from yesterday to tomorrow (by the UTC date). For each such season,
it checks the match broadcasts and season events dated today in the
season's time zone.

The task isolates each season, so one season's expired credentials do not
stop the others.

The task runs in a Celery worker, which is a different process from the web
server. The memory backend (`MemoryBackend`) cannot send events from one
process to another, so the pages do not see the changes that the task
finds. Use the Redis backend (`RedisBackend`) when you schedule the task.

The task checks the seasons of the schema that it runs in. Celery beat sends
its tasks from the public schema, where the task finds the seasons of no
tenant. In a multi-tenant project, schedule a task that sends
`refresh_all_live_stream_status` once for each tenant, in the schema of that
tenant. With the `CeleryApp` of
[tenant-schemas-celery](https://pypi.org/project/tenant-schemas-celery/), a
task that you send in `tenant_context` runs in the schema of that tenant:

```python
from celery import shared_task
from tenant_schemas.utils import (
    get_public_schema_name,
    get_tenant_model,
    tenant_context,
)

from tournamentcontrol.competition.tasks import refresh_all_live_stream_status


@shared_task
def refresh_every_tenants_live_stream_status():
    tenants = get_tenant_model().objects.exclude(schema_name=get_public_schema_name())
    for tenant in tenants:
        with tenant_context(tenant):
            refresh_all_live_stream_status.delay()
```

Put this task in `CELERY_BEAT_SCHEDULE` in place of
`refresh_all_live_stream_status`.

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
