# The harness

A local tool for judging the admin from pictures. Each branch gets its own
seeded database, its own dev server, a screenshot of every admin page at two
widths, and a video of one administrator's errand through the whole admin.
Two branches can then be compared side by side, page for page.

It lives in `harness/` and is never shipped: `MANIFEST.in` prunes it from the
sdist, and the wheel only packages the library. Nothing in it contacts a
remote service; the only network traffic is what a page asks the browser to
load (see Decisions). All data is made up.

You need PostgreSQL 17 binaries (Homebrew `postgresql@17` by default), a
virtual environment at `.venv/` with the project installed
(`uv sync --all-extras --group test`), and Playwright's Chromium for the
screenshots (`.venv/bin/playwright install chromium`).

## Quick start

Replace `demo` with any name you like. A name is lower-cased to `[a-z0-9_]`;
it picks the database `vitriolic_<name>` and the folders that belong to it.

```sh
harness/pg.sh start                     # 1. a temporary PostgreSQL (once per boot)
harness/db.sh demo                      # 2. create the database vitriolic_demo
harness/seed.sh demo                    # 3. migrate it and fill it with the made-up association
harness/serve.sh demo 8300              # 4. serve it; prints http://127.0.0.1:8300/admin/
harness/shots.sh --name demo --contact  # 5. screenshots, the flow video and contact sheets
harness/contact.sh <run-dir>            # 6. (only to re-tile; step 5 already did)
harness/stop.sh demo                    # 7. stop the server
harness/test.sh demo unit               # 8. the unit tests, with no Docker
```

Sign in at `/admin/` as `admin` with the password `password`.

Step 5 takes about 14 minutes: 153 pages and their tabs at two
widths (554 pictures), then the flow at each width. It prints one line
per capture and a summary, and writes everything to `run/demo/<brand>/` under
the state root (`<brand>` is the brand the server was started with, and
`<brand>-htmx` for a server started with `--htmx-tabs`; the root is
`~/.local/state/vitriolic-harness` unless `VITRIOLIC_HARNESS_VAR` says
otherwise). Use `--only` and
`--widths` for a quicker look, for example
`shots.sh --name demo --only season-edit,match-results --widths 1440 --no-video`.
`--only none` skips the pages and records only the flow; `--no-video` skips
the flow, which is what the video records.

The exit status of `shots.sh` is 1 when any page errored or any flow step
failed, or when fewer pages were captured than were listed (unless `--only`
said so), so on a branch with known faults a run is expected to exit 1. See
Known issues for the faults on the baseline.

## The scripts

All scripts are in `harness/`. Every executable script starts with
`set -euo pipefail` and prints usage on a wrong call (exit status 64).
`lib.sh` is not executable: it is sourced, sets no shell options, and reads
`BASH_SOURCE` to find its checkout, so it must be sourced from bash (from zsh,
run the work in `bash -c '...'`).

| Script | What it does |
| --- | --- |
| `lib.sh` | Shared by the others; source it from bash, do not run it. `harness_env` exports everything the demo project needs for a name; `harness_db_check <name>` exits 3, naming the owner, unless the name's database belongs to this checkout. |
| `pg.sh start\|stop\|status\|psql [name]` | A temporary PostgreSQL cluster in `pg/` in the state root, started with `pg_ctl`, never a service. `start` does nothing when the port already answers. `stop` stops only its own cluster. `psql` opens a shell on the server, or on the database of a name. |
| `db.sh [--reset] <name>` | Creates `vitriolic_<name>` and records the checkout that owns it. Exit status 3 when another checkout owns it; `--reset` takes it over, drops it and its media, run directory and pid file, and creates it again (it refuses while the name has a live server: stop it first). Prints `DATABASE_URL`. |
| `seed.sh <name>` | Migrates the database, then seeds it. Safe to run again: it adds only what is missing. About 20 seconds. Prints the number of rows of each model. |
| `serve.sh <name> <port> [--brand B] [--htmx-tabs]` | Runs `runserver --noreload` in the background and waits up to 30 seconds for the sign-in page. Refuses a port that is taken or a name that already has a server. Writes the pid file, which records the pid, port, brand, tab mode and checkout. |
| `stop.sh <name>` | Stops the server of a name, and only while the process is still its `runserver`. Not running is not an error. |
| `manage.sh <name> <args...>` | Runs the demo project's `manage.py` against the database of a name. |
| `shots.sh --name N [--base URL] [--brand B] [--htmx-tabs] [--widths 1440,390] [--height 900] [--only a,b\|none] [--no-video] [--contact] [--out DIR]` | Screenshots every page, records the flow, writes `manifest.json`, then removes the flow's rows from the database. Without `--base`, finds the server in the pid file. The pid file decides the brand and the tab mode: a `--brand` that disagrees is refused (exit 64); with `--base` and no pid file for that server, `--brand` is required. |
| `contact.sh <run-dir> [--width W] [--columns 4] [--tile-width 360] [--out FILE]` | Tiles a run's pictures at one width into one contact sheet. |
| `test.sh <name> [unit\|e2e] [--] [args...]` | Runs the tests through tox against the harness PostgreSQL, with no Docker. The name's database must exist and be yours. |
| `python -m harness seed\|pages\|unflow <stamp>` | The Python halves of `seed.sh` and `shots.sh`. Each checks the owner of the database first (exit 3). `unflow` deletes what one run of the flow made. |

Where things are kept, under the state root:
`pg/` the cluster, `media/<name>/` uploaded files, `log/<name>/server.log`,
`run/<name>/pid` the server, `run/<name>/<brand>/` a screenshot run
(`<brand>-htmx/` for a server started with `--htmx-tabs`, so the two modes
never replace each other), and `state/<name>/pages.json` the pages found for
the last run.

`shots.sh` refuses to write into a directory that is not an earlier run of the
same name, brand and tab mode. It replaces an earlier run of its own, and it
does so before anything else: a run that fails early (no server, discovery
failing) leaves an empty directory and a start manifest that says why, never
the pictures of the run before.

## Brands

The demo project can present the admin in three made-up brands. Choose one
with `serve.sh --brand` (this sets `ADMIN_BRAND`). `shots.sh` reads the brand
from the server's pid file.

| Brand | Name | Primary | Secondary | Logo |
| --- | --- | --- | --- | --- |
| `default` | Harbour Touch Association | `#275d8b` | `#e8862a` | The static logo (`img/logo.png`) |
| `forest` | Ridgeway Sports Trust | `#1e3d2f` | `#c9a227` | None: the name is shown as a text mark |
| `sherbet` | Bayside Junior League | `#ffd166` | `#073b4c` | None: the name is shown as a text mark |

They are defined in `tests/vitriolic/brands.py`. `--htmx-tabs` (the variable
`HTMX_ADMIN_TABS`) switches the tabbed edit forms to load each tab over HTMX.

## What the seed contains

An invented touch association, built through the admin toolset wherever it
offers a tool and through models or factories where it does not. Dates are
relative to the day of the first seed: the current season has played its
fifth round.

- **Clubs:** eight. **People:** 24, three per club, each with a club role
  (President, Secretary or Treasurer). 84 team associations (two per team,
  Captain and Coach, shirt numbers 7 and 9).
- **Competition:** one, the Harbour Touch League, with two seasons.
  - Autumn 2026: finished. Every match has a result, byes are processed, and
    the finals are played. Mixed Open has two pools of three teams, with
    cross-pool finals.
  - Spring 2026: in progress. Rounds 1 to 5 are played, including one draw,
    one forfeit and, in the Women's Open, one played match with no result.
    Round 6 is the next Wednesday, one to seven days after the seed day;
    round 7 and the finals are to come. A season-wide break and a Mixed Open break are set.
- **Divisions:** Men's Open (8 teams), Women's Open (7, so a bye each round)
  and Mixed Open (6). Each plays seven rounds, then finals. 172 matches in all.
- **Venues:** four (two per season, Anchor Park and Lantern Reserve) with ten
  grounds in all, at round invented coordinates that name no real ground, and
  four kick-off times a night with no clash of ground and time.
- **Extras on Spring 2026:** a season referee, a live stream key and event,
  and, on one Men's Open match, a score sheet and four statistics; a place
  waiting for a team in the Men's Open finals (an undecided team); and the
  officials two clubs named for the season (four rows).
- **Users:** `admin` (superuser), `editor` (the Editors group, which can
  edit pages and news) and `scorer` (can change matches and add score
  statistics). The password of each is `password`.
- **Content:** a home page with two child pages, a folder and an application
  node that points at the news site, three chunks (one of them
  the disclaimer the registration form shows) and a redirect.
- **News:** two categories, five articles (three with pictures) and one
  Spanish translation.
- **Enrolment:** the demo school (two school years, 21 classes, 300 students,
  attendance, assessments and report cards).

The pictures are drawn on the spot from a hash of their title; nothing is
downloaded.

## What `shots.sh` captures

The pages are found, not listed by hand (`python -m harness pages`): the
registered admin components, the admin URLs each model describes for itself,
the site tree's folder, page and application nodes, the content routes that
no model owns, and the named routes of the competition component that no
model owns. Every URL is reversed; none is guessed. The result is 153
pages:

- **static:** the index, sign-in, settings and the app indexes.
- **per model:** a list (where the model has one), an add page, an edit page
  for one instance and a permissions page.
- **site tree:** an edit, add and permissions page for a page node, an
  application node and (edit and add) a folder; the application
  configurations (list, add, edit) and the file manager.
- **auth:** the user and group lists and one of each.
- **named special pages:** match results, schedule, run sheet, grid (by day
  and for the season), visual scheduler, scorecards, washout, the match day's
  live stream, the scorecard report, season report and summary, progression,
  JSON builder, reschedule, scorers, bulk create of divisions and of teams,
  officials, registration form, person merge, draw build, progress matches,
  referees and the division detail.
- **tabs:** every page that has tabs gets one more picture per tab, named
  `<page>-tab-<n>-<width>.png`. Tabs are found on every captured page, not
  from a list: a `role="tab"` control, else the links of a `role="tablist"`,
  else (when there are two or more) the links to anchors of the page. Today's
  markup uses the last form. The discovery's `tabs: true` is only a hint: a
  page marked as tabbed that has no tabs gets the warning "no tabs found".
- **fold shots:** season-edit and match-results at 1440 also get the first
  screenful as `<page>-fold-1440.png`.

The sign-in page is photographed first at each width, before signing in, with
the same checks as every page (it must not redirect). The rest are
photographed signed in as `admin`.

The instance for a page is the Spring 2026 season, the division with the most
teams, a played match with a result, and a round robin stage.

Each page is photographed in full at 1440 and at 390 pixels wide. The run is
in the manifest, `manifest.json`: for each page its status, title, any final
URL (a redirect), the errors, and the warnings. An error is a page that does
not load, answers 4xx or 5xx, ends on the sign-in page, logs a console error
or an uncaught page error, or fails a request to the server under test. A
request to another host (a font, an avatar, a CDN script) is only a warning.

The manifest also says what kind of run it was, so a partial or stale set can
be told from a complete one by reading one file: `only` (the page names asked
for, `null` for all), `widths`, `video`, `expected_pages` (how many pages
`pages.json` listed), `checkout` and `commit` (where the run was made),
`htmx_tabs`, `flow_stamps` (for the clean-up below) and `errors` (what went
wrong with the run itself). It counts as failed when any page or step
errored, or when fewer pages were captured than `expected_pages` times the
widths and `--only` was not given.

Models and routes that cannot be given a page appear under `skipped` in
`pages.json`, each with a reason. On the baseline these are `Place` (the
parent of Venue and Ground, which has no admin route of its own),
`SeasonAssociation` (edited on its club's officials page, which is captured,
now with rows), `progress-teams` (no stage of the season gives that page) and
`upstream-sync`. The last is left out on purpose: it exists only for a season
with an upstream, and enabling one would make the page name a remote host to
fetch from, so the seed never does. A name in `skipped` is a gap in what the
run shows, not a failure.

## The flow

After the pages, `shots.sh` records one administrator's errand through the
admin at each width, to `flow-1440.webm` and `flow-390.webm` (about five
minutes each). The flow must survive an admin whose markup has been rewritten,
so every lookup is by role and accessible name (`get_by_role`), by visible
text (`get_by_text`), by link target (`a[href=...]`, `a[href$=...]`) or by
form field name (`[name=...]`, `get_by_label`). It never looks for an id, a
class or a data attribute first. The few that today's markup needs (the
sidebar of tabs, the two menu buttons, the profile drop-down, a row's
drop-down and undo button, and Select2's container) are in `LEGACY_FALLBACKS`
in `flow.py`, which is read only by `legacy_fallback`, and only after the
lookups by role, text, link target and field name have found nothing. A test
checks both rules. A 3 pixel ring marks where the pointer goes. How it looks:

- **A folded menu** is opened with a button named like a menu ("Toggle
  navigation", "Menu"), or any control that says so, or an `aria-expanded`
  button, trying each in turn until the entry (found by its text) is on show;
  with no such entry, the step goes `direct`.
- **A tab** is a `tab` by name, a link of that name in a `tablist`, a link to an
  anchor with that text, or any link or button of that name. A tab with a
  page of its own that is out of sight goes `direct`; a tab that cannot be
  found at all is a warning ("could not open the pane") and the step goes on.
- **Confirming** a delete or an undo presses the button of the dialog on show
  (a button whose name matches delete, undo, remove, confirm or yes), or of
  the page the click led to; a browser prompt is accepted.
- **Dates** are typed as the field takes them: an input of type `date` or
  `datetime-local` gets its ISO form, a text field's placeholder is read when
  it looks like `dd/mm/yyyy`, and otherwise Django's first date input format
  is used. A saved date is looked for in any of the usual forms.
- **A step whose target cannot be found** by any of these records `direct`
  with a one-line note naming what it looked for, goes to the address, and
  goes on.

What the flow expects of any admin, and so what an entry must keep: the
sign-in form's `username` and `password` fields and a "Sign in" button; a
"Save" button and a "Cancel" link; a `search` field on long lists; the menu
entries "Tournament Control", "News", "Content" and "Enrolment"; the form
field names of the models (which are frozen); and the URL paths. The steps,
in order:

1. **sign_in:** the sign-in page, then the index.
2. **competition:** add a competition.
3. **season:** add a season, with its time slots.
4. **clubs_and_people:** add two clubs, add them to the competition, and add
   people.
5. **divisions_and_teams:** bulk-create two divisions and their teams, and
   give a division a points formula.
6. **draw:** add a draw format, a stage, build the draw, then add a finals
   stage with a pool and an undecided team.
7. **schedule:** allocate the day's matches to grounds and times with the
   Allocate form.
8. **results:** enter two results and read them back.
9. **undo_draw:** undo the draw of a stage.
10. **content:** add a news category, an article with a picture and a
    translation, a redirect and a page.
11. **enrolment:** a school year, a grade, a teacher, a class, students,
    attendance, an assessment and a report card.
12. **delete_attendance:** delete an attendance record.
13. **sign_out:** sign out from the menu.

The flow checks what it saved: the titles are listed, the translation's
headline, the undecided team's label, the allocation and the scores are read
back from the forms, the marks of the assessment are on it when it is opened
again, and the attendance record is gone after the delete.

The manifest records for each step how it reached its page, in `via`:

- `link`: by clicking a visible link or button that leads there.
- `scroll`: the link or button that changes the page, or opens the tab, was
  out of view, so the page was scrolled to it first. Typing into a field
  below the fold does not count.
- `direct`: nothing on the page led there, so the step went to the address.

On the baseline no step has to go `direct`. In the last run 7 of the 13 steps went by link and 6 scrolled at
1440 and 5 went by link and 8 scrolled (none went direct at either width) at 390; the split moves a little with the data on the
page (a longer list pushes a link out of view). At 390 the folded menu is
opened first for any step that uses it. A step that raises ends the flow, and
a picture of the page is saved as `flow-<width>-failed.png`.

A step fails, and the run with it, on an uncaught page error, a console
error, a request to the server under test that fails, or a failed assertion,
exactly as a page capture does; a request to another host is a warning. A
step that only met such an error does not stop the flow, so the recording
still reaches its end. The one allowance is in Decisions.

**The flow cleans up after itself.** It adds a competition, a season, a draw
format, news, a page and enrolment rows to the database, and ends every
title and last name with its stamp (the time of day). It notes the stamp in
the manifest (`flow_stamps`) as it starts, and `shots.sh` then runs
`python -m harness unflow <stamp>` for each width, which deletes those rows
through the ORM and prints what it removed. So a capture always shows the
seed alone, and runs of one entry or of two can be compared page for page.
`unflow` accepts only six digits and is safe to run twice.

## Environment variables

| Variable | Default | Effect |
| --- | --- | --- |
| `VITRIOLIC_HARNESS_VAR` | `$XDG_STATE_HOME/vitriolic-harness`, else `~/.local/state/vitriolic-harness` | The state root. |
| `VITRIOLIC_PG_PORT` | `55432` | The port of the PostgreSQL server. |
| `VITRIOLIC_PG_USER` | `vitriolic` | The role. The cluster trusts local connections, so no password. |
| `VITRIOLIC_PG_BIN` | `/opt/homebrew/opt/postgresql@17/bin` | Where `initdb`, `pg_ctl`, `psql` and the rest are. |
| `HARNESS_PYTHON` | `<checkout>/.venv/bin/python` | The interpreter for the demo project. |
| `CLOUDINARY_URL` | `cloudinary://harness:harness@harness` | A dummy so image tags can build their URLs. Nothing is uploaded. |
| `ADMIN_BRAND` | `default` | The brand; `serve.sh --brand` sets it for the server. |
| `HTMX_ADMIN_TABS` | `0` | Load tabs over HTMX; `serve.sh --htmx-tabs` sets it. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | unset | `test.sh e2e` passes it through, to use a browser that is already installed. |

`harness_env` also sets `DATABASE_URL`, `DB_5432_TCP_PORT`, `MEDIA_ROOT`,
`COMPOPS_EVENTS_BACKEND=memory` and `PYTHONUNBUFFERED=1`.

## Running the tests

`test.sh <name> unit -- touchtechnology.admin enrolment` runs the Django tests
for those labels in `dj61-py314`. `test.sh <name> e2e -- e2e/test_admin_flow.py`
runs Playwright tests in the `e2e` environment, with the commentary events
held in memory instead of Redis. Both turn Docker off for tox, and point the
tests at the PostgreSQL that `pg.sh` started. Django makes the database
`test_vitriolic_<name>` for them and drops it afterwards. With no labels,
tox's default list runs: `touchtechnology.common`, `touchtechnology.admin`,
`touchtechnology.content`, `touchtechnology.news`,
`tournamentcontrol.competition` and `enrolment`.

The harness has tests of its own (`harness/test_*.py`). Run them from the
checkout root, in the environment of a name, from bash:

```sh
bash -c 'source harness/lib.sh; harness_env demo; .venv/bin/python -m pytest harness/ -q'
```

The tests that seed write their pictures to the name's `media/` folder; give
them a throwaway state root with `VITRIOLIC_HARNESS_VAR=/tmp/harness-tests`.

## Decisions

- **Synthetic data only.** Every name, picture and number is invented. The
  telephone numbers are from the reserved range for fiction.
- **The visual scheduler is captured but never driven.** Its page is
  photographed like any other, but dragging matches about is too fragile to
  record, so the flow uses the Allocate form.
- **Other hosts are not blocked, and their failures are warnings.** Some pages
  load Leaflet, Bootstrap and jQuery from a CDN, so blocking the network made
  false errors. On a machine with no network those pages (grounds, venues,
  the season report and summary) will report errors.
- **A temporary cluster, not a service.** `pg.sh` starts a cluster under the
  state root with `pg_ctl` and leaves other PostgreSQL servers alone.
- **One allowance.** `KNOWN_PAGE_ERRORS` in `flow.py` turns one uncaught page
  error into a warning, recorded with its text, so a recording reaches the
  end: `Cannot set properties of undefined (setting '_DT_CellIndex')`, matched
  against the whole text of the error and nothing else. The club edit page
  runs DataTables on a table whose only row is the empty-list message, and
  DataTables 1.10 cannot take that row. Every other uncaught page error, and
  every console error, fails the step.
- **Databases are owned by a checkout.** `db.sh` records the checkout that
  made a database, and `seed.sh`, `serve.sh`, `manage.sh`, `shots.sh`,
  `test.sh` and `python -m harness` all compare it with their own and exit 3,
  naming the owner, when it differs or is missing. So two worktrees that
  both follow the quick start with `demo` cannot migrate, serve or replace
  each other's data; the second `db.sh demo` says so, and `--reset` takes it
  over on purpose. The scripts do not guard against someone running
  `psql` directly.

## Known issues found while building

On the baseline, `shots.sh` exits 1 with 22 page-capture errors and no failed
flow steps (the run of 153 pages, 554 pictures and 26 steps).
The 22 errors are on six pages, each at both widths:

- `match-grid`, `match-grid-season` and `scorecards` link print stylesheets
  that are not served (404 for `css/reset-min.css`, `base-min.css`,
  `vi_grid.css`, `reset.css` and `base.css`).
- `report` and `summary` load Bootstrap's script before jQuery ("Bootstrap's
  JavaScript requires jQuery").
- `officials` loads `formset.js`, which needs MooTools, so it logs "Class is
  not defined".

Gaps in the admin that the flow found and works around:

- The editable team members page has no template. A valid save now
  redirects, but opening the page, or a save that fails validation, raises
  `TemplateDoesNotExist`.
- A club association cannot be added from a link (nothing links to the add
  page), and saving that form raises an `IntegrityError` because the club is
  not set on a new object.
- Teams cannot be placed in a pool from the UI. The team form has no pool
  field.
- The division page has no ladder.
- A division made by the bulk form has no points formula, so saving a result
  for it raises an error until one is set on the division.
- The seeded 3-team round robin leaves a team without matches when drawn for
  four teams, so the flow adds a four-team format first.

## What this branch fixed on the way

The harness found these in the library, so they are fixed here (each is its
own commit and could be taken on its own):

- The season officials page raised on an undefined read-only flag, linked to
  a route that does not exist (`club-teams`), and failed to build its empty
  form. Its save redirected to the same missing route.
- The team members save redirected to the same missing route.
- Score sheets are routed by their UUID, so a match with a score sheet can be
  edited.
- The news site is mounted in the demo project, so the news admin can link
  to articles.
