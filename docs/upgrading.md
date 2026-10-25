# Upgrading from 4.x

## The admin has shells

From 5.0 the admin is drawn by a *shell*: a complete set of templates, styles,
scripts and icons. The Python that drives the admin is the same for every
shell. The admin ships two, `workbook` (the default) and `explorer`. A
deployment chooses one when it builds its site:

```python
from touchtechnology.admin.sites import AdminSite

site = AdminSite(name="admin", shell="explorer")
```

The 4.x theme is gone. `touchtechnology/admin/shells.py` describes a shell.

## Admin templates moved into the shells

In 4.x the pages of the admin were at names that did not depend on a theme,
such as `touchtechnology/admin/list.html`. In 5.0 every page is in the folder
of its shell, such as `touchtechnology/admin/workbook/list.html`. The old names
are gone. A template that *extends* a page by its 4.x name fails with
`TemplateDoesNotExist`, unless the name is one of the four below.

### Names that still work, for now

These four names are kept as thin shims for a release or two. A shim holds no
markup. It extends the page of the same name in the folder of the shell the
admin wears. The shims will be removed in a later release, so change your
templates to the new names (see "How to extend a page now") when you can.

| 4.x name                          | The shim extends                          |
| --------------------------------- | ----------------------------------------- |
| `touchtechnology/admin/base.html` | `touchtechnology/admin/<shell>/base.html` |
| `touchtechnology/admin/list.html` | `touchtechnology/admin/<shell>/list.html` |
| `touchtechnology/admin/edit.html` | `touchtechnology/admin/<shell>/edit.html` |
| `40x.html`                        | `touchtechnology/admin/<shell>/40x.html`  |

`<shell>` is `workbook` or `explorer`.

A shim finds the shell in the `shell` variable of the template context. The
admin puts `shell` in the context of every page it renders itself: the pages of
the components, the home page, the sign-in page and the wizards. The
`touchtechnology.admin.context_processors.brand` context processor puts it in
the context of every template. Add that processor if you extend `40x.html`
from the error pages of your public site. When a template has no `shell`, the
shim extends the page of the default shell, `workbook`, even if the site wears
`explorer`.

### Names that are gone

These pages have no shim. Each one is now in the folder of the shell, under the
same name:

- `touchtechnology/admin/edit.multiple.html`
- `touchtechnology/admin/edit.related.html`
- `touchtechnology/admin/index.html`
- `touchtechnology/admin/permissions.html`
- `touchtechnology/admin/settings/index.html`
- `touchtechnology/admin/group/list.inc.html`
- `touchtechnology/admin/user/list.inc.html`
- `touchtechnology/admin/_htmx_tab_empty.html`
- `touchtechnology/admin/_htmx_tab_related.html`

For example, `touchtechnology/admin/edit.related.html` is now
`touchtechnology/admin/workbook/edit.related.html` and
`touchtechnology/admin/explorer/edit.related.html`. Two more changed:

- The `mvp` list templates were renamed. See "The `mvp` names are gone" below.
- `touchtechnology/admin/_version.html` is gone. `{% version_string %}` now
  returns the text itself.

The pages of the components moved in the same way. The template base of a
component is the folder of its admin pages, such as
`tournamentcontrol/competition/admin`. A page that was at `<template base>/<name>`
is now at `<template base>/<shell>/<name>`. For example,
`tournamentcontrol/competition/admin/base.html` is now
`tournamentcontrol/competition/admin/workbook/base.html` and
`tournamentcontrol/competition/admin/explorer/base.html`. The same is true of
`touchtechnology/content/admin/base.html`. The library keeps no copy at the old
name.

### The `mvp` names are gone

In 4.x the code that draws a list of related objects was named after the old
theme. The theme is gone, so the names are gone. The code does the same work.
Change these names in your project:

| 4.x | 5.0 |
| --- | --- |
| `{% load mvp_tags %}` | `{% load admin_lists %}` |
| `{% mvp_list ... %}` | `{% admin_list ... %}` |
| the `mvp_list_template` filter | the `admin_list_template` filter |
| `mvp/list.html` | `touchtechnology/admin/<shell>/_list.html` |
| `mvp/list.inc.html` | `touchtechnology/admin/<shell>/list.inc.html` |
| `mvp/list.split.inc.html` | `touchtechnology/admin/<shell>/list.split.inc.html` |
| `_mvp_related`, `_mvp_select_related`, `_mvp_prefetch_related`, `_mvp_only` and `_mvp_annotate` on a model | `_list_related`, `_list_select_related`, `_list_prefetch_related`, `_list_only` and `_list_annotate` |

The `related` filter keeps its name. The library keeps no copy at an old name.
A template that loads `mvp_tags` fails with `TemplateSyntaxError`. A template
that extends `mvp/list.inc.html` fails with `TemplateDoesNotExist`.

A model that still has an `_mvp_*` method gets no error. The admin ignores the
method, and the lists of that model run the untuned queries. Rename the
methods.

### Templates that replace a page

A template of yours that *replaces* a page of the admin is a different case.
Where the admin finds a page by searching, a template at the 4.x name still
wins, for either shell. The admin searches the template folders of a component
and then `touchtechnology/admin/`, so `tournamentcontrol/competition/admin/season/edit.html`
in your project is still chosen. This is how the admin finds `list.html`,
`list.inc.html`, `edit.html`, `edit.related.html` and `permissions.html`.

The admin does not search for some pages. It asks for them by name, in the
folder of the shell: the home page (`index.html`), the sign-in page, the HTMX
tab fragments and the list wrapper (`_list.html`). A template of yours at the 4.x name of
one of these no longer replaces it. Put your template in the folder of the
shell.

### How to extend a page now

To change a page for both shells, put your template at the name the admin
looks for, and extend the page of the shell in the context:

```django
{% extends shell.template_dir|add:"/list.html" %}
```

`shell` is in the context when the admin renders the page (see above). For a
page of a component, add the name of the shell to the folder:

```django
{% extends "tournamentcontrol/competition/admin/"|add:shell.name|add:"/base.html" %}
```

To change a page for one shell, put your template at the name in the folder of
that shell, and extend the page of the same name. Django finds the page of the
library when a template extends its own name:

```django
{# templates/touchtechnology/admin/explorer/list.html #}
{% extends "touchtechnology/admin/explorer/list.html" %}
```

### Blocks

Every block that the 4.x `base.html`, `list.html` and `edit.html` defined is
still in both shells. What a block holds is now the markup of the shell, not
Bootstrap 3, so check each template that fills a block in both shells. A block
that a page does not define is ignored without an error.

The full notes for the change are in pull request #392.

## The `NODE_CACHE` setting is gone

5.0 removes the `TOUCHTECHNOLOGY_NODE_CACHE` setting and the
`Placeholder.invalidate_cache()` method. Nothing has written to that cache
since 2018, when the sites of the application nodes stopped being cached.
After an application node was edited, the content admin cleared the whole
cache. With the default value, `"default"`, that cleared every key of the
default cache, for every tenant.

The cached URL tree of the sitemap is now thrown away for one tenant at a
time. It is thrown away when a node, competition, season, club, division or
team of that tenant is saved or deleted.

Remove `TOUCHTECHNOLOGY_NODE_CACHE` from your settings. If no other code uses
the cache it named, remove that cache from `CACHES` too. The library ignores
the setting if you keep it, and shows no error. Code that calls
`invalidate_cache()` fails with `AttributeError`.

The full notes for the change are in pull request #422.

## The staff pages of the public site are gone

In 4.x the public competition site (`CompetitionSite`) had pages for staff:
result entry, per-player statistics, stage progression, live-stream control,
runsheets and a page where a team member forfeits a match. 5.0 removes them.
Staff do this work in the admin and in CompOps.

There are no redirects. Below the URL of a season, these paths are now unknown
paths, and the site returns 404 for them:

| Path | URL name | The page that is gone |
| --- | --- | --- |
| `results/` and `results/<YYYYMMDD>/` | `results` | The times that wait for results |
| `results/<YYYYMMDD>/<HHMM>/` | `match-results` | Result entry for one time |
| `results/match/<id>/` | `match-details` | Per-player statistics for a match |
| `results/progress/` | `progression-list` | The stages that wait for progression |
| `results/progress/<division>/<stage>/` | `progress-teams` | Progression of a stage |
| `stream/` and `stream/<YYYYMMDD>/` | `stream` | The times that have live streams |
| `stream/<YYYYMMDD>/<HHMM>/` | `stream-control` | Start, test and stop the live streams of one time |
| `runsheet/` and `runsheet/<YYYYMMDD>/` | `runsheet` | The runsheet of a day |
| `forfeit/` | `forfeit-list` | The matches a team member can forfeit |
| `forfeit/<id>/` | `forfeit` | Forfeit a match |

A template that reverses one of these names fails with `NoReverseMatch`. This
is true for the full name, such as `{% url "competition:results" ... %}`, and
for the name made from the application, such as
`{% url application.name|add:":results" ... %}`. Remove the link.

These templates are gone. A template of yours at one of these names is no
longer used:

- `tournamentcontrol/competition/results.html`
- `tournamentcontrol/competition/match_detail.html`
- `tournamentcontrol/competition/progression_list.html`
- `tournamentcontrol/competition/progress_matches.html`
- `tournamentcontrol/competition/stream.html`
- `tournamentcontrol/competition/runsheet_list.html`
- `tournamentcontrol/competition/runsheet.html`
- `tournamentcontrol/competition/forfeit_list.html`
- `tournamentcontrol/competition/forfeit.html`

The admin's pages with the same file names are in
`tournamentcontrol/competition/admin/<shell>/`. They stay.

Two names are gone from the Python:

- `StreamControlForm` in `tournamentcontrol.competition.forms`.
- `CompetitionAdminMixin` in `tournamentcontrol.competition.sites`. The admin's
  views `day_runsheet`, `match_results`, `edit_match_detail`,
  `progression_list` and `progress_teams` are now methods of
  `CompetitionAdminComponent` in `tournamentcontrol.competition.admin`. Their
  URLs, permissions and templates in the admin did not change.

Issue #310 lists the stream control page as one of the pages that raise an
error when the YouTube authorisation of a season has expired. That part of
#310 goes away with the page.

### Where staff do the work now

| The page that is gone | Admin | CompOps |
| --- | --- | --- |
| Result entry | Yes. The day's results page (`admin:fixja:match-results`), the Awaiting Scores widget and the season's Schedule tab. | Yes. The results panel of the day page, the page of a time and the page of a match result. |
| Per-player statistics | Yes. The detailed results of a match (`match:detail`) and the detailed results widget. | Yes. The scorers of a match. |
| Stage progression | Yes. The season's progression list and the progress page of a stage. | No. |
| Start, test and stop a live stream | No. The live stream page of a day (`match-live-stream`) sets up the day's streams, and `resync-live-stream` sends them to YouTube again. No page of the admin changes the status of a broadcast. | Yes. The streams page, the stream controls of a time and of a match, and the booth. |
| Runsheet | Yes. The run sheet of a day (`match-runsheet`), to print. | Yes. The day page. |
| A team member forfeits a match | Partly. Staff can record a forfeit on the match. A team member has no page that calls `Match.forfeit()` and sends its notifications. | No. |

The REST API can also start, test and stop a broadcast:
`POST /api/v1/livestreams/<uuid>/transition/`, for a user with
`competition.change_match`.

There are two more gaps:

- **Scorers who are not staff.** The public pages accepted a user with the
  permission `competition.change_match`, for all matches or for one match
  (with `django-guardian`). The user did not have to be staff. Result entry in
  the admin and in CompOps needs staff status. A volunteer scorer who is not
  staff can no longer enter results.
- **CompOps is optional.** A project must mount CompOps (see `docs/compops.md`).
  Until it does, staff have only the admin, and no page starts or stops a
  live stream.

The full notes for the change are in pull request #437.

## The `en-AU` catalogues are gone

The apps no longer ship `locale/en-AU`. Django never loaded those catalogues,
because it looks for a directory named `en_AU`, and they held no translations.
A project that offers `en-au` in `LANGUAGES` sees no change: these apps show
their source strings, as before.
