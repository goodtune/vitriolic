# Admin design brief

vitriolic is a public, open-source set of Django applications for sporting
club and competition websites. Its administration interface, the
`touchtechnology.admin` component and every screen that extends its shell
(competition, content, news, users, groups and permissions), is built on a
licensed theme over Bootstrap 3 and jQuery. The theme is licensed and
Bootstrap 3 is long dead, so the whole presentation layer is being replaced.
The replacement is also a redesign of the administrator's experience.

Three designers each build a complete alternative on their own branch. The
owner chooses from screenshots and recordings. The winner, or a fold of two
entries, becomes the next major version of the admin.

## Public project, invented data

This repository is public. Use only what is in it. Do not look up, name,
link to or imitate any organisation that runs this software; every
organisation, club, venue, person, school and colour you will see in the
seeded data is invented, and anything you add must be invented too. That
applies to commit messages, templates, screenshots, the entry statement and
any issue or PR text.

## Who uses it

A competition administrator or a club volunteer. Mostly at a desk, and
increasingly on a phone or tablet at the ground. They operate software:
they set up a season, build a draw, schedule a day, enter a day's results,
keep clubs, teams and people current, and publish news and pages. App
conventions are welcome. This is the application tier, not the public site.

A deployment also registers its own admin components. The demo project
includes one, a school enrolment system (school years, grades, teachers,
class groups, students, enrolments, attendance, assessments with scores,
report cards). It is not a product; it proves that a component vitriolic
does not ship renders well in your design, both through the generic views
alone and through one custom template that uses the documented extension
points. Your design must serve it as well as it serves competitions.

## What is judged

UX is half the mark.

- **Moving around the hierarchy without hunting.** Competition, season,
  division, stage, pool, match; clubs, teams, people; venues, grounds; and in
  the enrolment app school year, grade, class group, student. Today a person
  moves up a level with a Cancel link at the foot of the form, which is often
  off screen. Where you are and where you can go must always be visible.
- **The administrator's jobs first.** Set up a season, build and schedule a
  draw, enter a day's results, keep clubs and people current, publish.
- **Bulk creation as a normal path.** Divisions, teams and stages can
  already be added many at once; design for "add many" at every level.
- **Choosing things.** Picking from a set (a person, a team, an image)
  belongs in a dialog with search, not an inline wall of options.
- **Forms work without JavaScript.** Every form is a plain HTTP post that
  works with scripts disabled; enhancement comes after.
- **Both widths excellent.** 1440 px and 390 px are each designed, not one
  stretched or squeezed into the other.

The rest of the mark is craft:

- Designed for an operator, not a template. Consistent actions in
  consistent places; dense where density helps; tabular figures in tables.
- Accessible: AA contrast on every one of the three brands, visible focus,
  landmarks, keyboard reachable, reduced motion respected.
- Branded: the deployment's name, logo and palette colour the whole
  interface through the branding contract described in FOUNDATION.md.
  You are judged on all three demo brands, including the pale one.
- Every page green in the screenshot run: no failed loads, no redirects to
  sign-in, no 4xx or 5xx, no console errors.
- Your entry statement: direction, the structural changes you made, UX
  decisions per page type, fonts and how colours derive from the palette,
  proposals that would need model or deployment changes, rough edges.

Not judged: the visual scheduler (below), the public site, the compops
site, the MCP servers. The standalone print and report pages are judged for
legibility and consistency with your system only, not for UX.

## The rule for an entry

Your branch is `admin/<slug>`. You may change:

- templates and static files anywhere under `touchtechnology/` and
  `tournamentcontrol/competition/` that the admin renders;
- views, forms, template tags, context processors and the admin shell's
  Python in `touchtechnology/admin`, `touchtechnology/common/sites.py` and
  each app's `admin.py`, as far as the new structure needs;
- the `admin` extra in `pyproject.toml` and the system check in
  `touchtechnology/admin/apps.py`. Bootstrap must go, so `django-bootstrap3`
  goes with it; `django-gravatar2` is your call. A deployment that still
  lists either in `INSTALLED_APPS` must not error.
- the demo project's templates if you must override something, never its
  models;
- the extension points a deployment's custom templates use (blocks, tags,
  filters, context keys). If your UX changes, so do the foundations of an
  external app. Migrate every in-repo user, including the enrolment app's
  custom template, and write a migration note in your statement saying what
  a deployment changes. Landing the winner is a major version bump.

You may not change: models or migrations; any existing URL name or path
(deployments reverse them; new names and paths are welcome); the MCP
servers; the public site (`touchtechnology/common/templates/base.html` and
the competition, content and news public pages); the compops site; the
visual scheduler.

`TOUCHTECHNOLOGY_HTMX_ADMIN_TABS` keeps being accepted. What it does under
your structure is your call, written down in the statement. The
`?_htmx_tab=` fragment endpoint is not a kept contract: if you replace the
tab mechanism, replace the tests that prove it (the mode comparison in
`tests/e2e/admin_tabs.py` and friends) with tests that prove your own lazy
loading, and say so. That is a rewrite, not a deletion.

**The visual scheduler is exempt.** The drag-and-drop grid that allocates a
day's matches to time slots and grounds (URL name `match-visual-schedule`,
view `match_visual_schedule`, template `admin/match/visual_schedule.html`,
stylesheet `visual_schedule.css`, and its e2e performance and colour tests)
opens in its own tab, does not follow the current theme, and its
performance took several rounds to get right. Keep it exactly as it is,
including its Alpine script from the CDN, link to it as today, and spend no
time on it.

**The standalone print and report pages are in scope.** The printable match
matrix (`match-grid`), run sheet, season report and summary, scorers,
progression list, the JSON division builder and the calculator do not
extend the shell and load their assets from CDNs today. Restyle them in
your system, self-hosted, print-friendly where they are printed. The
screenshot run captures them; the flow recording does not visit them.

The registration site's `rego/` templates are dead: `RegistrationSite` has
no URL patterns. Delete or restyle them as you please.

Technique: server-rendered HTML with HTMX partials. No React, no SPA
framework, no build step. Vanilla JavaScript where needed. Self-host every
font, icon set and script you use so a run is reproducible; Gravatar
avatars are per-user content you may keep or replace with initials, and a
failed Gravatar fetch is a warning, not a failure.

Nothing of the old theme may survive: not a stylesheet fragment, not a
class name, not a script.

The full suite must be green for the latest combination (`tox -e
dj61-py314`) and the e2e suite (`tox -e e2e`). A test that asserts the old
markup may be rewritten to assert yours, provided it still proves the same
thing; a test may not be deleted to pass. The enrolment app's permission
sweep must stay green.

A steer, not a rule: navigation that spends vertical space on a top bar is
a known dislike of the owner; a left rail has been preferred.

## Your seeded direction

Interpret it freely, but keep the three entries distinct.

- **Console** (`console`): the operations desk. Dense, keyboard-friendly,
  tables with tabular figures, a jump-to search that lands on any object in
  the hierarchy, consistent actions in consistent places. For the
  administrator at a desk; still usable one-handed on a phone.
- **Explorer** (`explorer`): the hierarchy is the interface. A persistent
  tree (competition, season, division, stage, pool; organisation, school
  year, grade, class group) beside the page, like a file manager, every
  level reachable from it; collapses to drill-down on a phone.
- **Workbook** (`workbook`): task-led and friendly for the volunteer.
  Setting up a season is a checklist with progress; generous spacing and
  type; phone first, then a real desktop layout.

## What to deliver

1. The branch `admin/<slug>`, in small commits whose messages describe the
   behaviour.
2. A green screenshot run at 1440 and 390 for each of the three brands, and
   the flow recording, made with the harness (see FOUNDATION.md for the
   commands and where the output lands).
3. The entry statement at `docs/design-contest/entries/<slug>.md`, under
   500 words: direction; structural changes made; UX decisions per page
   type; fonts and colour derivation; the migration note for deployments;
   proposals needing model or deployment changes; rough edges.
4. The suites green.

Read FOUNDATION.md next. It names the extension points, the branding
contract, the models that have no page of their own, the harness, and the
seams the foundation left for you.
