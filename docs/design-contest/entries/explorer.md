# Explorer

## Direction

The hierarchy is the interface. A rail beside every page holds the whole admin
as a tree, like a file manager: each component is a folder, its sections are
folders inside it, then the objects down to the page you are on. Competition,
season, division, stage, pool; a season's venues and match days; clubs and
their people; school year, grade, class group, enrolment; the site's pages.
The current place is filled with the brand colour, the way to it is drawn in
ink, and the location bar repeats it. On a phone the rail folds behind Menu
and becomes a drill-down, one folder at a time.

## Structural changes

- `touchtechnology/admin/explorer.py` builds the tree from the admin's nested
  URLs, so a deployment's component gets one with no code; `explorer_class`,
  `Rel` and `Folder` refine it (competition, content, enrolment do). Folders
  open over a new `admin:explorer` endpoint. It reuses the objects a page
  holds: one query per open folder.
- New shell, stylesheet, script, SVG icons, print stylesheet. Bootstrap,
  jQuery, Select2, iCheck, DataTables, Font Awesome and the theme's logo are
  gone, with `django-bootstrap3` and `django-gravatar2` (initials instead).
- Save and Cancel sit in the sticky page head; on a phone, in the top bar.
  Delete, undo and "add several" ask in a native dialog. Forms post without
  scripts.
- The flow ran with no `direct` and no `scroll` at either width.

## Page types

- **Objects**: Details, then a tab per relation, counted and remembered.
  Divisions gain a Ladder tab; seasons a Schedule of match days.
- **Match days**: Results, Allocate, Washout, Live stream and the prints, with
  the day before and after. Results read as a scoreboard by kick-off; a card
  per match on a phone.
- **Lists**: dense tables, tabular figures, row menus, "Add several" beside
  "Add" wherever bulk creation exists, another-row buttons on bulk pages.
- **Choosing**: a select of many options, or of several, opens a dialog
  with a search; chosen items show as chips.
- **Print sheets**: one header and brand rule, A4-ready tables.

## Type and colour

IBM Plex Sans (variable, self-hosted, OFL), narrowed slightly in the rail;
its figures are tabular. Every colour derives in `oklch()` from the five brand
properties: text colours cap the brand's lightness at 0.43, so they pass AA on
any palette; text on a brand fill is white or near black by the fill's
lightness, so pale sherbet carries dark text; focus rings take the secondary.

## Migration note

- Extend `touchtechnology/admin/list.inc.html` (`mvp/` names remain as
  aliases); block names are unchanged, but `row-buttons-items` holds links
  and forms, not `<li>`.
- A tab: `{% include "touchtechnology/admin/_tab.html" with name=… label=… %}`
  in `tab-links`; its pane `<section class="pane" data-tab-panel
  role="tabpanel" id="<name>-tab">` in `tab-panes`, as the student page does.
- Drop `bootstrap3` and `django_gravatar` from `INSTALLED_APPS` when ready.
- `TOUCHTECHNOLOGY_HTMX_ADMIN_TABS` still fetches a pane when its tab is first
  shown.
- Edit pages no longer offer Delete; rows do.

## Proposals needing model or deployment changes

A pool field on the team form; a default points formula for bulk divisions;
`__str__` for exclusion dates and time slots; a landing page per component.

## Rough edges

Deep enrolment paths truncate in the rail; long sections list forty objects
then link to the rest; the query-count tests' ceilings rise by the explorer's
open folders.
