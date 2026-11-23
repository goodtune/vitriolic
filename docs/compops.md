# Tournament Ops

`tournamentcontrol.competition.compops` is a mountable site for running a tournament day: a results and live-stream dashboard for the ops desk and a commentary booth per streamed ground.
Pages update live over Server-Sent Events using [Datastar](https://data-star.dev) (vendored, 1.0.4); the rest of the admin is untouched.

## Mounting

```python
# urls.py
from tournamentcontrol.competition.compops.sites import CompOpsSite

urlpatterns += [path("compops/", CompOpsSite().urls)]
```

Install the extra: `pip install vitriolic[async]` (adds `datastar-py` and `redis`).
Nothing happens unless the site is mounted.

Add `"touchtechnology.common.middleware.DatastarMiddleware"` to `MIDDLEWARE`; it sets `request.datastar`, and `CompOpsSite()` raises `ImproperlyConfigured` without it.

Do not use `"django.middleware.gzip.GZipMiddleware"`. It compresses each chunk of an async stream as a separate gzip member, and browsers decode only the first.
The page gets its opening snapshot and no live update after it.
Use `"touchtechnology.common.middleware.GZipMiddleware"` in its place.
It leaves `text/event-stream` responses uncompressed and compresses everything else as Django's does.
To leave out more types, subclass it and extend `excluded_content_types`. The system check `tournamentcontrol.competition.E005` fails while Django's is in `MIDDLEWARE`.

The templates use template partials (`{% partialdef %}` and `{% partial %}`) without `{% load %}`, and the views render a partial by name, for example `day.html#results`. Django 6.0 and later have partials built in and need no settings.
Django 5.2 needs three settings, set out in [Template partials on Django 5.2](#template-partials-on-django-52).

The booth refuses an action with a normal 200 response that carries the reason in the lamp.
Datastar drops the body of non-200 responses, so a refusal that used an error status would never reach the page.
The lamp, like a ground's block in the day page's streams column and a result row with an open Edit or a refused save, is then held: the snapshot a reconnect sends passes over it, and the next action, or a push about the same ground or match, releases it.
The template comment above `match_row` in `day.html` explains the mechanism.

## Pages

The site has three levels, each leading down to the next.

- The home page (`compops:index`) lists every season, whether or not it is enabled.
  The seasons being played come first, each with a button that opens today's page, or the next day with matches on a rest day.
  The next five seasons to start and the last five to end follow, and then every season under its competition.
  A season with no dated matches appears only in that last list.
- The season page (`compops:season`) lists the season's days with matches.
  Each day shows how many matches it has and whether its results are all in, still to enter today, or missing from a day gone by.
  Those who may open the season's booths get a link to them.
- The day page (`compops:day`) is the dashboard.
  In its streams column, each ground's name leads to that ground's booth for those who may open it.
- A booth (`compops:booth`) shows today at its ground.
  A stream usually starts before its match does, to introduce it.
  So when nothing is on air, and no match that has kicked off is still to be ended, the lamp is the next match's: it names that match, shows STANDBY once the match is armed, and puts it on air before its kick-off time.
  It follows the ground: its lamp is the match on air, or the next to go, and its strip is the match before, the match now and the match after by the clock.
  The match now changes at the next match's kick-off time, not when a match ends.
- A booth opened on one match (`compops:booth-match`) is that match's, whatever the clock says.
  Its lamp, its buttons and its panes are about that match, and its strip is the matches either side of it.
  Each match in a strip or a runsheet is a link to its own booth, so a commentator can be sent the address and get set before their match starts.
  One match of a ground is on air at a time: while another is, the view says which, links to it and offers no button to go on air.
  The page sends its match as the `view` signal with every request it makes, its event stream among them; "Follow the ground" leads back.
- The arrows in a booth's header step to the ground's nearest earlier and later days with matches, as `?day=YYYYMMDD`.
  Another day's booth is for looking over: it shows that day's matches and panes, and has no button that acts on the broadcast.
  Its top bar leads back up to the season and the home page, and steps to the nearest earlier and later days with matches.

Someone who is not staff gets a shorter home page: the seasons whose booths they may open, each leading to its booths (see [Who can do what](#who-can-do-what)).

A season is placed by the date where it is played, from its `timezone`.
Any day of any season can be opened, so a past day can be corrected or shown in training, and a coming one explored before it starts.

## Scoreboards

Every ground of a season has a scoreboard: the score of the match being played, and a clock that counts its periods down.

| Page | Route | For |
| --- | --- | --- |
| The board | `compops:scoreboard` | a large screen at the ground |
| The overlay | `compops:scoreboard-overlay` | a layer over the live stream: one bar, with nothing behind it |
| The scorer | `compops:scorer` | a phone, with a button to add one and to take one off for each team |

`compops:scoreboard-index` lists a season's grounds with a link to each page.

### The score

The scoreboard keeps a progress score on the match (`home_team_progress_score` and `away_team_progress_score`).
It is not the result.
The result is still `home_team_score` and `away_team_score`, entered on the ops page, and only the result moves a ladder.
Until a progress score is kept, the board shows the result if the match has one.

Each press of a scorer's button is published on a channel of its own, `season:<id>:scoreboard`.
The boards of that ground are sent the new score at once.
The ops desk's activity does not list the presses.

### The clock

Nothing is stored or pushed for the clock while it runs.
It counts from one moment, through the periods and breaks of the match's division:

- A division gives `periods` (2 unless changed), `period_minutes` and `break_minutes`.
- A stage, or one match, may give any of the three for itself.
  Each number is the match's own if it has one, else its stage's, else its division's.
  Rugby sevens plays halves of 7 minutes and its final halves of 10, so the finals stage (or the final alone) sets a period length of 10 and takes the rest from the division.
- A match that gets no period length from any of them has a board with the score and no clock.

The board names each period from how many the match has:

| Periods | Each is called | The breaks |
| --- | --- | --- |
| 1 | nothing: no name is shown, and no dots | none |
| 2 | 1st Half, 2nd Half | Half time |
| 4 | 1st Quarter to 4th Quarter | Quarter time, Half time, Three-quarter time |
| any other | 1st Period, 2nd Period and so on | Break |

"Period name" on a division, a stage or a match gives another word for a sport that has one: with "Chukka" the periods are 1st Chukka, 2nd Chukka and so on, and each break is a Break.
Like the timing, the name is the match's own if it has one, else its stage's, else its division's.
- A venue has "Start scoreboard clocks on time" (`scoreboard_auto_start`), which is on unless changed.
  With it on, the clock runs from the match's scheduled time.
  With it off, the clock waits until the scorer presses "Start the clock".

The server works out where the clock is each time it renders the board, and the page's script counts on from the same numbers.
The server sends its own time too, so a screen whose clock is wrong still counts correctly.

A break starts the moment a period ends.
Before a match and between periods, the clock counts down to the next start in another colour.
In the last minute of a period the clock shows seconds to a tenth (`59.9` down to `0.0`).
The dots under it are the periods and the breaks between them.
A horn sounds when a period starts or ends; a browser plays no sound until the page has been touched, so the board has a button to turn the horn on.

### Which match the board shows

The board shows the match being played on its ground.
Before the first match of the day, and from two minutes after a match's clock ends, it shows the next match with a countdown to its start.
A match with no clock, or whose clock was never started, keeps the board until the next match's scheduled time.
The page asks for the board again every 20 seconds, so it moves on by itself.

### Branding

Override the small templates the board includes, in `tournamentcontrol/competition/compops/scoreboard/`:

| Template | Where | Given |
| --- | --- | --- |
| `_brand.html` | above the score | `season`, `ground` |
| `_logo.html` | each team's circle | `team` (`None` until it is decided), `code` |
| `_sponsors.html` | below the clock | `season`, `ground` |
| `_style.html` | in the page's head | nothing; set the `--sb-` variables of `scoreboard.css` in a `<style>` |

Leave `scoreboard.html` as it is.
The live updates find the score, the clock and the dots by the ids in its `board` partial, and the script counts the clock from the data attributes of `#sb-clock`.

No model has a logo yet, so `_logo.html` shows a few letters for the team: its club's abbreviation, else the start of its name.

A project can also replace the whole page for every board of the site: put its own `tournamentcontrol/competition/compops/scoreboard.html` ahead of this one on the template path.
That template must keep the `board` partial, and inside it the ids and the data attributes of `#sb-clock`.

### Write a whole page in the admin

A competition, a season, a division and a stage each have a "Scoreboard template" field in the admin.
It holds a whole page, as a Django template, that draws the boards of that scope in place of the usual one.
The template nearest the match is used: its stage's, else its division's, else the season's, else the competition's, else the project's template.
A ground with no match today takes the season's, else the competition's.

`docs/examples/scoreboard-split.html` is a template to start from: the scores on the left, the clock on the right, the event's badge above the clock, and a picture behind them.

The look is the designer's.
The live updates need four things of the template, and it is the designer's work to keep them:

| In the template | What it is for |
| --- | --- |
| `{{ scripts }}` in the head | Datastar and the clock's script |
| `{{ attrs }}` on the `<body>` | opens the event stream |
| `{% board %}` and `{% endboard %}` | around the part that changes during a match; the updates replace what is between them |
| `{{ clock_attrs }}` on the clock's element, with `#sb-time` inside it | what the script counts the clock from, and where it writes the time |

`#sb-label` (the phase's name, such as "1st Half"; empty for a match of one period), `#sb-dots` (one `li` for each period and break; `dots` is empty for a match of one period) and `#sb-sound` (the button that turns the horn on) are used if they are there.
The script sets the class of the clock's element to the phase (`before`, `period`, `break`, `over` or `ready`), for the template's styles to colour.
`{{ styles }}` is the usual style sheet, for a template that wants to start from the usual look.

The form tries a template before it saves it, and refuses one that does not compile or has no `{% board %}`.

A template written in the admin is given less than a template of the project's, because whoever may edit a stage may write one:

- It has Django's own tags and filters and `{% board %}`.
  It cannot `{% load %}` a tag library, or include or extend another template.
- It is given plain values, never a model: `competition`, `season`, `venue` and `ground` (each a `title`, most a `slug`), `match` (`pk`, `time`, `label`, `round`, `division`, `stage`), `home` and `away` (`name`, `code`, `score`), `clock` (`periods`, `period_minutes`, `break_minutes`), `moment` (`kind`, `label`, `display`, `period`), `dots` and `variant` (`display` or `overlay`).
  A model would let a template read anything it leads to, such as a season's YouTube secrets.

Images are the designer's to host: a template names them by address, or draws them itself as the example does.

A page that is open takes up a new template by itself.
Each board says which template drew it; when an update brings a board drawn by another, or by an edited one, the page loads itself again.

### Not yet

The clock cannot be paused or put right, there is no extra time, and the progress score is not offered as the result when a match ends.

## Template partials on Django 5.2

Skip this section on Django 6.0 and later.

On Django 5.2 the partials come from [django-template-partials](https://pypi.org/project/django-template-partials/) 25.3 or later.
Install it yourself.
A dependency cannot be limited to one Django version, so the `async` extra leaves it out.

Three settings go together, and each fails in its own way when it is missing:

| Setting | When it is missing |
| --- | --- |
| `"template_partials"` in `INSTALLED_APPS` | `CompOpsSite()` raises `ImproperlyConfigured` when the URLconf loads |
| `"template_partials.templatetags.partials"` in the `builtins` of the template `OPTIONS` | the pages fail with `TemplateSyntaxError`: `Invalid block tag ... 'partialdef'` |
| the template loaders wrapped in `template_partials.loader.Loader` | the live updates fail with `TemplateDoesNotExist`, as they render a partial by name |

### A project that sets no loaders

This is the usual case, with `APP_DIRS` or without it.
Add the app and the builtins:

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

Nothing else is needed.
When Django starts, the app removes `APP_DIRS` and puts the filesystem and app directories loaders, inside a cached loader, inside its own loader.
It finds the engine by its name, which for `DjangoTemplates` is `django`. An entry with a different `NAME` is left alone: wrap its loaders as in the next section.

### A project with its own loaders

The app replaces `loaders` that are not wrapped yet.
It does this without a message, and it uses its own list, so a loader of yours is gone and its templates are not found.
Wrap your loaders yourself, before you add the app:

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

- The `template_partials.loader.Loader` entry must be the first loader, and it must be a tuple (or list) of the loader and the loaders it wraps.
  A cached loader around it, or a plain string, does not work.
- Put all your loaders inside it, including the cached loader if you use one.
  A loader outside it never sees the `#name` of a partial.
- Remove `APP_DIRS`. Django does not accept `APP_DIRS` and `loaders` together.
  Add `"django.template.loaders.app_directories.Loader"` to the list instead.

### Checks

When the URLconf mounts `CompOpsSite`, `manage.py check` reports a missing setting with the lines to add: `tournamentcontrol.competition.E002` for the builtins and `E003` for the loaders.
The app needs no check, as `CompOpsSite()` refuses to mount without it.
The check reports nothing on Django 6.0 and later, and nothing when the site is not mounted.

It finds the site by its app name, `compops`. A site that you mount under another `app_name`, or from a content node (a database row), is not seen.
To turn a check off, put its id in `SILENCED_SYSTEM_CHECKS`.

## Who can do what

| Page or action | Needs |
| --- | --- |
| Ops dashboard pages | login and `is_staff` |
| The home page | login, and `is_staff` or a booth permission on some season |
| Enter or edit a result | `is_staff` and `competition.change_match` on the match (guardian object or global) |
| Enter scorers | `is_staff`, `competition.add_simplescorematchstatistic` and `change_simplescorematchstatistic` |
| Start, test or stop a broadcast; whole-slot actions | `is_staff` and `competition.stream_season` on the season |
| Watch the booth: the lamp, the strip, the runsheet and the panes | login and `competition.commentate_season` (or `competition.stream_season`) on the season; staff status is not needed |
| See a ground's scoreboard or its overlay | nothing; anyone with the address may |
| Keep a scoreboard: change the score, start the clock | login and `competition.score_season` on the season; staff status is not needed |
| Go on air, end the broadcast or arm the next one from the booth | login and `competition.stream_season` on the season; staff status is not needed |

Every dashboard action is part of the dashboard, so it needs `is_staff` as well as its own permission.
Only the booth works without staff status.

Both booth permissions are season permissions, held for one season (a guardian object permission) or for every season (a global permission).
A permission on a season covers every streamed ground and every match of that season.

`competition.commentate_season` is for people who follow the broadcast but do not run it, such as a communications team.
They see the on-air lamp, kept live, and the team sheets, results, ladder and leaders, with no button that acts on the broadcast.
The home page (`compops:index`) is their front door: for someone who is not staff it lists only the seasons whose booths they may open, each leading to its list of booths (`compops:booth-index`).
It refuses someone with no such season, and the rest of the site refuses anyone who is not staff.
Grant it to a group, and add people to the group:

```python
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm

comms = Group.objects.get(name="Comms team")
assign_perm("competition.commentate_season", comms, season)
```

Grant a scorer `competition.score_season` in the same way; it lets them keep the scoreboard of every ground of the season, and nothing else.

Grant the commentator pair who run the broadcast `stream_season` in the same way:

```python
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

The two `events/` endpoints are async streaming views and need an ASGI server. granian 2.8.3 or later:

```
granian --interface asgi --workers 2 --http auto myproject.asgi:application
```

`manage.py runserver` is WSGI and cannot serve the streams; for local work use `granian --reload --interface asgi` or `uvicorn --reload`.

Behind nginx, disable buffering for the stream locations (the responses also send `X-Accel-Buffering: no`) and set `proxy_read_timeout` above the keep-alive interval.
Serve HTTP/2 to browsers so one person can keep the ops page and two booths open.
Do not put `GZipMiddleware` in front of the streams.

The `events/` endpoints log and keep streaming when a single push fails to render.
They also validate their database connection around each push.

## Tenants

On a [django-tenant-schemas](https://pypi.org/project/django-tenant-schemas/) site, one event bus serves all the tenants.
Each tenant has its own tables, so two tenants can have a season with the same id.
The bus keeps the events of each tenant apart: it names the channel of a season from the schema that the database connection points at.
For season 3, the Redis backend uses these names:

| Site | Channel | Recent events |
| --- | --- | --- |
| The tenant with the schema `alpha` | `compops:alpha:season:3` | `compops:alpha:season:3:recent` |
| A single-tenant site | `compops:season:3` | `compops:season:3:recent` |

An event goes to the tenant whose schema the connection points at when the event is published.
A request to the site of a tenant points the connection at the schema of that tenant.
Outside a request, use `tenant_context`, or a Celery task that runs in the schema of the tenant.
An event that is published in the public schema goes to the public schema only, and no tenant's page shows it.

## Broadcast status

`Match.live_stream_status` and `LiveStreamEvent.live_stream_status` record YouTube's lifecycle status after every transition made from the site.
Both columns are 20 characters wide and store YouTube's `lifeCycleStatus` values, including the transient `liveStarting` and `testStarting`. The site writes the status without model signals, so a stream transition does not recalculate ladders.

Changes made in YouTube Studio are picked up by the Celery task `tournamentcontrol.competition.tasks.refresh_all_live_stream_status`; schedule it every minute:

```python
CELERY_BEAT_SCHEDULE = {
    "refresh-live-stream-status": {
        "task": "tournamentcontrol.competition.tasks.refresh_all_live_stream_status",
        "schedule": 60.0,
    },
}
```

The task checks each season with `live_stream=True` that has matches dated from yesterday to tomorrow (by the UTC date).
For each such season, it checks the match broadcasts and season events dated today in the season's time zone.

The task isolates each season, so one season's expired credentials do not stop the others.

The task runs in a Celery worker, which is a different process from the web server.
The memory backend (`MemoryBackend`) cannot send events from one process to another, so the pages do not see the changes that the task finds.
Use the Redis backend (`RedisBackend`) when you schedule the task.

The task checks the seasons of the schema that it runs in.
Celery beat sends its tasks from the public schema, where the task finds the seasons of no tenant.
In a multi-tenant project, schedule a task that sends `refresh_all_live_stream_status` once for each tenant, in the schema of that tenant.
With the `CeleryApp` of [tenant-schemas-celery](https://pypi.org/project/tenant-schemas-celery/), a task that you send in `tenant_context` runs in the schema of that tenant:

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

Put this task in `CELERY_BEAT_SCHEDULE` in place of `refresh_all_live_stream_status`.

## Tests

Unit tests are plain django-test-plus `TestCase` classes; the SSE views are tested with `async def` methods and `self.async_client`. The e2e tests run under a uvicorn server started in the test process (`asgi_live_server` in `tests/e2e/conftest.py`) because the WSGI `live_server` cannot serve an endless stream.
The fixture bounds uvicorn's shutdown with a one second graceful timeout.
The e2e tox environment runs Redis in docker and uses the Redis backend. `tox -e e2e` declares its containers with one `docker = db` entry and one `docker = redis` entry, one per line.
