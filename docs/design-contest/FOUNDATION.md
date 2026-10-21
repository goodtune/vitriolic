# What the foundation gives you

Read BRIEF.md first. This document names the things the contest base
provides, the seams it leaves for you, and the rig you run.


## The admin shell today

- Shell: `touchtechnology/admin/templates/touchtechnology/admin/base.html`
  (top navbar with a profile dropdown, a `mainnav` built from
  `admin.get_components`, a breadcrumbs block, messages, content).
- Generic pages: `index.html`, `list.html`, `edit.html` (a tab sidebar: the
  edit form, then one tab per related manager from `object|related:related`,
  lazy over HTMX when `TOUCHTECHNOLOGY_HTMX_ADMIN_TABS` is on),
  `edit.related.html`, `edit.multiple.html`, `permissions.html`, the
  `_htmx_tab_*.html` fragments.
- Cancel is `cancel_url` in the context, set per view in
  `touchtechnology/common/sites.py` and
  `tournamentcontrol/competition/admin.py`. Only 13 admin templates write
  breadcrumbs.
- Static today: Bootstrap 3, jQuery, select2, iCheck, slimscroll, flot,
  DataTables, slick, `formset.js`, `URI.js`, Font Awesome 4, the theme's
  three scripts and stylesheet, `custom.css`/`custom.less`. All of it goes.
- Generic views: `touchtechnology/common/sites.py` (`generic_list`,
  `generic_edit`, `generic_edit_related`, `generic_delete`,
  `generic_permissions`); `touchtechnology/admin/base.py`
  (`AdminComponent`); `touchtechnology/admin/mixins.py` (`AdminUrlMixin`,
  which gives models their `urls`).
- Two wizards, `DrawGenerationWizard` and `ScorecardWizardBase`, render
  through their own `TemplateResponse` rather than
  `AdminComponentMixin.render`; anything you put in the render context
  (see `field_template` below) is not there unless you add it.
- The stock `edit.html` never renders a form's `non_field_errors`. Fix it
  in your design.
- Signed-in non-staff users are redirected to the sign-in page by
  `staff_login_required_m`; staff without a model permission get 403.

## Admin-owned rendering seams (yours to change)

The public site shares nothing with these; leave
`touchtechnology/common/templates/**` alone.

- **Field template.** `{% field %}` reads `field_template` from the
  context and falls back to the public template. The admin's copy is
  `touchtechnology/admin/templates/touchtechnology/admin/templatetags/field.html`;
  `AdminComponentMixin.render` and `AdminSite.index` set `field_template`
  to it.
- **Form base.** `touchtechnology.admin.forms.AdminFormControlMixin` is
  `AdminComponent.model_form_bases`; it extends the public
  `BootstrapFormControlMixin` today and is the place to put the admin's
  widget and attribute policy. `Application.required_form_bases` (and
  `get_required_form_bases()`) is what the "your form must inherit from…"
  check compares against; the admin's value accepts either mixin so
  explicit forms on the common mixin do not log errors.
- **List includes.** `_list.html`, `list.inc.html` and `list.split.inc.html`
  live in the folder of each shell, under `touchtechnology/admin/templates/`,
  and are used only by the admin. `{% admin_list %}` (in `{% load admin_lists %}`)
  is the tag that includes them.
- **Sign-in.** `admin:login` and `admin:logout` (POST only) are thin
  wrappers of Django's auth views with the admin-owned template
  `touchtechnology/admin/templates/touchtechnology/admin/login.html`. The
  demo project's `LOGIN_URL` points at `admin:login`; `accounts:login` is
  untouched and still renders under the public site. Signing in without a
  `next` lands on the admin index. Password change and the profile pages
  stay where they are; link to them. A signed-in staff
  user who visits the sign-in page is sent on; a signed-in non-staff user
  sees the form with a notice naming the account.

## The branding contract

`touchtechnology.admin.branding`:

- `Brand(name, logo, colours)`, frozen. `name` defaults to
  "Administration"; `logo` is a static path or URL and defaults to
  `img/logo.png` (the logo the shell has always shown), or `None` to show
  the name as a text mark; `colours` is a mapping over `COLOUR_KEYS`
  (`primary`, `secondary`, `success`, `warning`, `danger`), `#rrggbb`
  only, filled from `DEFAULT_COLOURS` where a key is absent.
- Setting `TOUCHTECHNOLOGY_ADMIN_BRAND`: a mapping, a `Brand`, a callable
  taking the request, or a dotted path to one. A per-request identity can
  also set `request.admin_brand`. `get_brand(request)` resolves them in
  that order; `brand_from(value)` validates a single value.
- Invalid colours fail at startup (system check `touchtechnology_admin.E001`)
  and at resolution, never as a half-rendered page.
- The context processor `touchtechnology.admin.context_processors.brand`
  puts `brand` in every template; `render` and `index` also set it; and
  the shell resolves it itself when neither did (the wizards render that
  way), so the brand is never missing. The resolved brand is memoised on
  the request.
- The shell emits, from `_brand.html`:

  ```css
  :root {
    --brand-primary: …; --brand-secondary: …;
    --brand-success: …; --brand-warning: …; --brand-danger: …;
  }
  ```

  Derive every other colour from these (`color-mix()`, `oklch()`,
  relative colour syntax). Never hard-code a brand colour. Keep AA
  contrast on any palette.
- The navbar shows the logo if one is set, otherwise the name; the
  `brand_logo_url` filter in `touchtechnology/admin/templatetags/admin.py`
  resolves static paths. Of the demo brands, `default` has the static
  logo; `forest` and `sherbet` show the text mark.
- The demo project's brands, selected with `ADMIN_BRAND`:

  | key | name | primary | secondary |
  | --- | --- | --- | --- |
  | `default` | Harbour Touch Association | `#275d8b` | `#e8862a` |
  | `forest` | Ridgeway Sports Trust | `#1e3d2f` | `#c9a227` |
  | `sherbet` | Bayside Junior League | `#ffd166` | `#073b4c` |

  `sherbet` has a pale primary on purpose: white text on it fails AA, so
  your derivation has to notice.

## The demo project and the enrolment app

The demo project is `tests/vitriolic` (settings, urls, `manage.py` in
`tests/`), excluded from the wheel. It mounts the admin at `/admin/`, the
accounts site, static files and media. `DJANGO_DB_WAIT=0` skips its
start-up sleep when you run `manage.py` yourself.

The enrolment app is `tests/enrolment`: a deployment-style
`AdminComponent` registered from `EnrolmentConfig.ready`, namespace
`admin:enrolment`. Models: `SchoolYear`, `Grade`, `Teacher`, `ClassGroup`,
`Student`, `Enrolment`, `AttendanceRecord`, `Assessment`, `Score`,
`ReportCard`. Nested URLs follow the hierarchy
(`year/<year_id>/class/<pk>/…/enrolment/…/attendance|report/…`).

- `Score` has no page of its own; it is edited inline on the Assessment
  page through `generic_edit_related`.
- The component uses flat URL namespaces (`admin:enrolment:<model>`), so it
  carries one `list.inc.html` override per nested model. That is a
  deliberate test of the list-include extension point: do not "fix" it by
  changing the component's URL names.
- `edit_schoolyear` puts `year` in the context; the class-group tab's Add
  link is gated on it.
- The student edit page has a custom template,
  `tests/enrolment/templates/enrolment/admin/student/edit.html`, extending
  the stock `edit.html` and adding a Timeline tab through the `tab-links`
  and `tab-panes` blocks. It is the one in-repo consumer of the extension
  points outside vitriolic's own apps: if you change the points, migrate
  it, and write the migration note.
- `tests/enrolment/tests/test_admin.py` holds a table-driven permission
  sweep over every URL name the component registers (anonymous → sign-in,
  staff without permission → 403, wrong parent → 404). Keep it green.
- Seed: `seed_enrolment [--students N]`, idempotent, about three seconds.

## Demo project environment
- The news site is mounted at `news/` in the demo project so the news
  admin can link to published articles; the accounts site at `accounts/`;
  the admin at `admin/`.
- The harness exports a dummy `CLOUDINARY_URL` so scoresheet image fields
  render; nothing is uploaded, and a request to the Cloudinary host is a
  warning in the shots run, not a failure.

## Models with no page of their own

The shots driver reads this list; a missing page for these is not a
failure. You may add pages; you need not.

- Competition: `LadderEntry`, `LadderSummary` (read-only on the division);
  `UndecidedTeam` (inside the draw); `SimpleScoreMatchStatistic` (from the
  match); `SeasonAssociation` (the officials page); `Place` (the parent of
  `Venue` and `Ground`, never edited directly). `MatchScoreSheet` is
  reached from the match (its routes now take the model's UUID pk).
  `ClubRole` and `TeamRole` do have pages of their own.
- Content: `Content`, `PageContent`, `NodeContent` (inside the page editor);
  `Page` is reached through its `SitemapNode`.
- Enrolment: `Score` (inline on the Assessment).

The harness writes the list it actually found to `pages.json` (`skipped`,
with a reason per model) each time it discovers pages; that file, not this
paragraph, is what the shots driver trusts.

## Bugs the foundation fixed on the way

The page sweep found and fixed, on the contest base, pages that were a 500
for everyone: the season officials page (an undefined read-only flag, dead
links to a route that does not exist, and the save redirect to the same),
the team members save redirect, and the scoresheet routes. If your design
touches those views, keep the fixes. Still open and pre-existing: the
editable team-members page has no template (an expected-failure test
covers it); it is not in the captured page list.

## What the baseline run shows about today's admin

The harness ran the whole errand on the current admin. Every step
completed and none had to jump by URL, but about half the steps found
their link only after scrolling (6 of 13 at 1440, 8 of 13 at 390): the
Cancel link and the related tabs sit below the fold on many pages at 1440
and on most of them at 390. The baseline page captures carry 22 errors, all
in the legacy print and report pages (stylesheets that do not exist,
Bootstrap loaded before jQuery, a formset script that expects MooTools).
Things today's admin cannot do, which your design may or may not take on
(say which in your statement): add a club association from any link (its
save also fails); place teams in a pool from the interface; show the
ladder on the division page; save a result for a bulk-created division
until a points formula is set.

## Dead templates

`RegistrationSite` (`tournamentcontrol/competition/sites.py`) has no URL
patterns, so nothing under its `rego/` templates can be reached. Delete or
restyle them.

## The harness

`harness/README.md` is the manual; read it once, top to bottom. In outline,
from your entry's checkout, with `<name>` your entry's slug:

```sh
harness/pg.sh start                       # a temporary PostgreSQL, once per boot
harness/db.sh <name>                      # the database vitriolic_<name>, owned by this checkout
harness/seed.sh <name>                    # migrate and seed; idempotent, ~20 s
harness/serve.sh <name> <port> --brand forest   # default | forest | sherbet; add --htmx-tabs to test that mode
harness/shots.sh --name <name> --contact  # every page at 1440 and 390, the flow video, contact sheets, manifest.json
harness/stop.sh <name>
harness/test.sh <name> unit               # tox without Docker; `e2e` for the browser suite
```

- The run lands in `run/<name>/<brand>/` under the state root
  (`~/.local/state/vitriolic-harness` unless `VITRIOLIC_HARNESS_VAR` says
  otherwise; `run/<name>/<brand>-htmx/` for a server started with
  `--htmx-tabs`): one PNG per page and width, one more per tab on every
  page that has tabs, two fold shots at 1440, `flow-1440.webm`,
  `flow-390.webm`, `contact-1440.png`, `contact-390.png`, and
  `manifest.json` with every page's status, title, errors and warnings,
  every flow step's `via`, and the run's own metadata (`only`, `widths`,
  `expected_pages`, `checkout`, `commit`, `htmx_tabs`). `shots.sh` reads
  the brand from the server's pid file; a `--brand` that disagrees is
  refused.
- The sign-in page is captured first at each width, before signing in,
  with the same checks as every other page.
- `shots.sh` exits 1 when any page errored, any flow step failed, or fewer
  pages were captured than discovery listed. Your entry must exit 0 on all
  three brands at both widths. The baseline does not (see below).
- The flow cleans up after itself: it stamps every title and last name it
  creates and `shots.sh` runs `python -m harness unflow <stamp>` after each
  width, so every capture shows the seed alone and two runs compare page
  for page. `--only none` records the flow without the pages; `--no-video`
  the pages without the flow.
- The page list comes from `python -m harness pages` (153 pages on the
  base): the registered components, every `AdminUrlMixin` model's list,
  add, edit and permissions pages, the site tree's nodes and the content
  routes no model owns (placeholders, the file manager), the auth pages,
  the competition's named special pages (results, schedule, run sheet,
  grid, scorecards and the scorecard report, the match day's live stream,
  report, summary, officials, person merge, draw wizard, bulk create, and
  so on, including the exempt visual scheduler for completeness), and
  `skipped` with a reason per model or route that has no page.
  `upstream-sync` is skipped on purpose: it exists only for a season with
  an upstream, and setting one would name a remote host to fetch from. Pages you add under existing components are discovered
  automatically if they follow the same URL conventions; a page you add
  elsewhere is not captured unless you teach `pages.py` about it, and the
  judge only sees what is captured.
- The driver signs in through `admin:login` with the fields `username` and
  `password` and a submit button named "Sign in"; keep those, a "Save"
  button and a "Cancel" link on forms, a `search` field on long lists, and
  the menu entries "Tournament Control", "News", "Content" and "Enrolment".
  Tabs are found on every page by `role="tab"`, then the links of a
  `role="tablist"`, then links to anchors; if your design has no tabs,
  nothing is clicked and nothing fails. Menu entries are found by their
  visible text; at 390 the driver opens a folded menu through a button
  named like a menu ("Menu", "Toggle navigation") or any `aria-expanded`
  button before looking. Every lookup is by role, accessible name, visible
  text, link target or field name; today's ids and classes are consulted
  only as a last fallback, so restyle freely but keep roles and names
  meaningful. A console error or a failed request to the server under
  test fails a flow step exactly as it fails a page capture.
- Other hosts are not blocked: a request to a CDN or to Cloudinary that
  fails is a warning. Self-host your assets so your run is clean.
- One allowance exists for the baseline only, named in the README under
  Decisions; your run gets no allowances.
- Your entry's name, database and port:

  | entry | name | port |
  | --- | --- | --- |
  | baseline (today's admin) | `baseline` | 8300 |
  | `console` | `console` | 8301 |
  | `explorer` | `explorer` | 8302 |
  | `workbook` | `workbook` | 8303 |

The flow recording is one errand through the whole admin, following links
on the page: sign in; create a competition and its roles; a season with
exclusion dates, time slots, a venue with two grounds; clubs and people;
bulk-create divisions and teams; a draw format, stages and pools; place
teams and run the draw wizard; schedule a day; enter results and check the
ladder; publish an article and a page; then the enrolment app end to end
(school year, grade, class group, enrol students, attendance, an
assessment with scores, a report card); then a delete from a tab and the
return. Each step records how it got there (`link`, `scroll` when the link was
off screen, `direct` when nothing on the page led there and it went by
URL); every `direct` is visible to the judge.
