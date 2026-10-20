# Workbook

**Direction.** A volunteer's workbook: every page says where it is and what to do next. Big type, one task per sheet, Save always in reach. Phone first; the desk gets a rail and side columns.

**Structure.**
- Shell: a rail in the brand's colour (components, the open component's sections, account and Sign out at its foot); on a phone, a slim bar and a Menu drawer. Every page opens with a trail built from its address; an object crumb links to the tab that lists the page below it.
- Edit pages: heading, tabs with counts, then sheets. The form bar (title, Cancel, Save) sticks to the top; a second Save waits at the foot; every add form offers *Save and add another*. Rarely used fields fold away.
- Lists: tables at a desk, cards on a phone; row actions beside a menu (Delete last); sortable columns; long tab lists filter as you type.
- Choosing: long and multiple selects open a searchable dialog; the select stays in the form. Deletes and undos confirm in a dialog.
- Checklists: a season's set-up (nine steps, counted from the data, each linked to its place) and a division's (points formula first). New: division Ladder tab, Tournament Control hub, home-page jobs from each component (`AdminComponent.tasks`), club Officials tab (saving one no longer fails).
- Match day: results grouped by kick-off with large score boxes; allocation a row per match; both return to the season's match days.
- Print pages share one print base.

**Type and colour.** Atkinson Hyperlegible Next (reading, tabular figures), Bricolage Grotesque (headings), Lucide icons, Leaflet: all self-hosted. Every colour derives from `--brand-*` with relative OKLCH: paper and ink tinted by the primary's hue; the rail is the primary, nudged out of the lightness band where neither black nor white text reaches 4.5:1; the accent is the primary capped at L 0.46; state text capped near L 0.45, washes near L 0.96. Audited at AA on all three brands.

**HTMX tabs.** Related panes still load on first show through `?_htmx_tab=`; the mode tests read the new markup.

**Migration note.** Remove `bootstrap3` and `django_gravatar` from `INSTALLED_APPS` (harmless if kept). In `tab-links`, include `touchtechnology/admin/_tab.html` with `name`, `label` (and `count`); panes are `<section class="wb-pane wb-sheet" role="tabpanel" id="<name>-pane">`; `#<name>-tab` links still open a tab. List includes keep their blocks; `row-buttons-items` are `<li><a>` with `{% icon %}` (`{% load admin_ui %}`), Delete is `row-buttons-delete`, Add is `_add.html`; new blocks `table-head-actions` and `filter`. Use `{{ form.media|admin_media }}`. The enrolment app's list includes and student template are migrated.

**Proposals (models or deployment).** Default points formula for bulk-created divisions; `__str__` for `ClubAssociation` and a plural for `LadderEntry`; a delete route for officials; `Placeholder.module` without an `AttributeError`; per-stage pool membership for teams.

**Rough edges.** Without scripts a delete posts at once (no confirmation). Each tab count is a query. The flow's notes on pools, the ladder and officials are fixed text; the pool page already places teams. The visual scheduler is untouched.
