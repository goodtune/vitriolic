# Explorer

## Direction

The hierarchy is the interface. A rail beside every page holds the whole admin
as a tree: each component is a folder; inside are its sections, then the
objects, down to the page you are on. Competition, season, division, stage,
pool; venues and match days as folders of a season; clubs and their people;
school year, grade, class group, enrolment; the site's own page tree. The
current place is filled with the brand colour, its ancestors are drawn in ink,
and the location bar above the title repeats the path. On a phone the rail
folds behind a Menu button and becomes a drill-down, one folder at a time.

## Structural changes

- `touchtechnology/admin/explorer.py` builds the tree from the admin's own
  nested URLs: a deployment's component gets one with no code. A component
  may refine it (`explorer_class`, `Rel`, `Folder`); competition, content and
  enrolment do. Folders open over a new `admin:explorer` endpoint.
- One shell (`base.html`), one stylesheet, one script, an SVG icon sprite, a
  print stylesheet. Bootstrap 3, jQuery, Select2, iCheck, DataTables, Font
  Awesome, the theme and its logo are gone, with `django-bootstrap3` and
  `django-gravatar2` (initials replace avatars).
- Save and Cancel live in the page head, which stays in view; on a phone in
  the top bar. Delete, undo and "add several" ask in a native `<dialog>`;
  every form still posts without scripts.
- The flow ran with no `direct` and no `scroll` at either width.

## Page types

- **Object pages**: Details first, then one tab per relation with counts; the
  tab is remembered when you return. Divisions gain a Ladder tab; seasons a
  Schedule tab of match days.
- **Match days**: a bar of Results, Allocate, Washout, Live stream and the
  prints, with the day before and after. Results are a scoreboard grouped by
  kick-off; on a phone each match is a card.
- **Lists**: dense tables, tabular figures, row menus, "Add several" beside
  "Add" wherever bulk creation exists, another-row buttons on bulk pages.
- **Choosing**: a select of more than ten options, or of several, opens a
  dialog with a search.
- **Print sheets**: one header, brand rule, A4-friendly tables.

## Type and colour

IBM Plex Sans (variable, self-hosted, OFL), narrowed slightly in the rail;
its figures are tabular. Every colour is derived in `oklch()` from the five
brand properties: text colours cap the brand's lightness at 0.43 so they pass
AA on any palette; text on a brand fill switches between white and near black
at lightness 0.63, so the pale sherbet primary carries dark text; focus rings
come from the secondary colour.

## Migration note

- Extend `touchtechnology/admin/list.inc.html` (the `mvp/` names remain as
  aliases). Its block names are unchanged; `row-buttons-items` now holds
  plain links and forms, not `<li>` items.
- A tab is `{% include "touchtechnology/admin/_tab.html" with name=… label=… %}`
  in `tab-links`; its pane is `<section class="pane" data-tab-panel
  role="tabpanel" id="<name>-tab">` in `tab-panes`. The enrolment student
  template shows both.
- Remove `bootstrap3` and `django_gravatar` from `INSTALLED_APPS` at will.
- `TOUCHTECHNOLOGY_HTMX_ADMIN_TABS` still fetches each pane when its tab is
  first shown (`hx-trigger="shown once"`).

## Proposals needing model or deployment changes

A pool field on the team form; a default points formula for bulk divisions;
`__str__` for exclusion dates and time slots.

## Rough edges

Very deep enrolment paths truncate in the rail; large sections list forty
objects then link to the full list.
