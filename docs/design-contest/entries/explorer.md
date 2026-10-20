# Explorer

## Direction

The hierarchy is the interface. A rail beside every page holds the admin as a
tree, like a file manager: components, their sections, then the objects down
to the page you are on. Competition, season, division, stage, pool; a
season's venues and match days; clubs and people; school year, grade, class
group, enrolment; the site's pages. The current place takes the brand
colour, the way to it is inked, and the location bar repeats it.
On a phone the rail folds behind Menu into a drill-down, one folder at a time.

## Structural changes

- `touchtechnology/admin/explorer.py` builds the tree from the admin's nested
  URLs, so a deployment's component gets one with no code; `explorer_class`,
  `Rel` and `Folder` refine it. Folders open over a new `admin:explorer`
  endpoint; one query per open folder.
- New shell, stylesheet, script, SVG icons, print stylesheet. Bootstrap,
  jQuery, Select2, iCheck, DataTables, Font Awesome and the theme's logo are
  gone, with `django-bootstrap3` and `django-gravatar2` (initials instead).
- Save and Cancel sit in the sticky page head; on a phone, in the top bar.
  Delete, undo and "add several" ask in a native dialog. Forms post without
  scripts.
- The flow needed no `direct` and no `scroll` at either width.

## Page types

- **Objects**: Details, then a counted, remembered tab per relation.
  Divisions gain a Ladder; seasons a Schedule of match days.
- **Match days**: Results, Allocate, Washout, Live stream and the prints, with
  the day before and after. Results read as a scoreboard by kick-off.
- **Lists**: dense tables, tabular figures, row menus, "Add several" beside
  "Add" wherever bulk creation exists.
- **Choosing**: a select of many options opens a dialog with a search.
- **Print sheets**: one header, A4-ready tables.

## Type and colour

IBM Plex Sans (variable, self-hosted, OFL), narrowed in the rail; tabular
figures. Every colour derives in `oklch()` from the brand properties: text
colours cap the brand's lightness at 0.43, so they pass AA on any palette;
text on a brand fill is white or near black by the fill's lightness, so pale
sherbet carries dark text; focus rings take the secondary colour.

## Migration note

- Extend `touchtechnology/admin/list.inc.html` (`mvp/` names remain as
  aliases); blocks are unchanged, but `row-buttons-items` holds links and
  forms, not `<li>`.
- A tab: `{% include "touchtechnology/admin/_tab.html" with name=… label=… %}`
  in `tab-links`; its pane `<section class="pane" data-tab-panel
  role="tabpanel" id="<name>-tab">` in `tab-panes`, as the student page does.
- `bootstrap3` and `django_gravatar` are no longer needed; listed, they are harmless.
- `TOUCHTECHNOLOGY_HTMX_ADMIN_TABS` still fetches a pane when first shown.
- Edit pages no longer offer Delete; rows do.

## Proposals needing model or deployment changes

A pool field on the team form; a default points formula for bulk divisions;
`__str__` for exclusion dates and time slots; a landing page per component.

## Rough edges

Deep enrolment paths truncate in the rail; long sections list forty objects
then link to the rest; query-count ceilings rise by the open folders.

## Round 2

Adopted Workbook's set-up checklist, made to fit the tree. A season,
competition and school year gain a Set-up tab: numbered steps, each saying
what is done or missing ("Mixed Open has no matches yet") and linking to the
page or tab that completes it, the next one marked. Every page inside a
season or school year (division, stage, pool, team, class) shows that
parent's progress bar and next step under its title, so the tree says where
you are and the bar says what is left. `touchtechnology/admin/setup.py` holds
the steps; it is all server-rendered.
