# Workbook

**Direction.** A volunteer's workbook: every page says where it is and what to do next. Big type, one task per sheet, Save always in reach. Phone first; the desk gets a rail and side columns.

**Structure.**
- Shell: a rail in the brand's colour holding the tree (Round 2), account and Sign out at its foot; on a phone, a slim bar and a Menu drawer. Every page opens with a trail; an object crumb links to the tab listing the page below it.
- Edit pages: heading, tabs with counts, then sheets. The form bar (title, Cancel, Save) sticks to the top; a second Save waits at the foot; every add form offers *Save and add another*. Rarely used fields fold away.
- Lists: tables at a desk, cards on a phone; row actions beside a menu (Delete last); sortable columns; long tab lists filter as you type.
- Choosing: long and multiple selects open a searchable dialog; the select stays in the form. Deletes and undos confirm in a dialog.
- Checklists: a season's set-up (nine steps, counted from the data, each linked to its place) and a division's (points formula first). New: division Ladder tab, Tournament Control hub, home-page jobs from each component (`AdminComponent.tasks`), club Officials tab (saving one no longer fails).
- Match day: results grouped by kick-off with large score boxes; allocation a row per match; both return to the season's match days.

**Type and colour.** Atkinson Hyperlegible Next (reading, tabular figures), Bricolage Grotesque (headings), Lucide icons, Leaflet: all self-hosted. Every colour derives from `--brand-*` with relative OKLCH: paper and ink tinted by the primary's hue; the rail is the primary, nudged out of the lightness band where neither black nor white text reaches 4.5:1; the accent is the primary capped at L 0.46; state text capped near L 0.45, washes near L 0.96. Audited at AA on all three brands.

**HTMX tabs.** Related panes still load on first show through `?_htmx_tab=`; the mode tests read the new markup.

**Migration note.** *Updated for the merged code base, where Workbook is the shell `"workbook"` (the default).* Remove `bootstrap3` and `django_gravatar` from `INSTALLED_APPS` (harmless if kept). Templates live under `.../admin/workbook/`; a template at the old, shell-neutral path still overrides the shell's page at that level, and wins over it. In `tab-links`, include `touchtechnology/admin/workbook/_tab.html` with `name`, `label` (and `count`); panes are `<section class="wb-pane wb-sheet" role="tabpanel" id="<name>-pane">`; `#<name>-tab` links still open a tab. List includes (`touchtechnology/admin/workbook/mvp/list.inc.html`) keep their blocks; `row-buttons-items` are `<li><a>` with `{% icon %}` (`{% load admin_workbook %}`, renamed from `admin_ui`), Delete is `row-buttons-delete`, Add is `_add.html`; new blocks `table-head-actions` and `filter`. Use `{{ form.media|admin_media }}`. The enrolment app's list includes and student template are migrated.

**Proposals (models or deployment).** Default points formula for bulk-created divisions; `__str__` for `ClubAssociation` and a plural for `LadderEntry`; a delete route for officials; `Placeholder.module` without an `AttributeError`; per-stage pool membership for teams.

**Rough edges.** Without scripts a delete posts at once (no confirmation). Each tab count, and each open folder, is a query. The flow's notes on pools, the ladder and officials are fixed text; the pool page already places teams. The visual scheduler is untouched.

**Round 2: the tree.** Adopted from the Explorer entry, with credit: `touchtechnology/admin/explorer.py` is its builder (nodes found from the admin's nested URLs, a few lines per component), drawn with Workbook's icons. At a desk the rail is the tree: the page's component opened down to where you are (competition, season, division, stage, pool; site pages; school year, grade, class), that place a paper tab the rail opens onto; other folders open in place. On a phone, Menu opens a drill-down at the page's folder, with "Up to" and a way into each folder. Checklists unchanged. Fixed: the rich-text editor starts on article and page copy.
