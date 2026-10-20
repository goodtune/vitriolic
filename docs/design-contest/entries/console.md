# Console

**Direction.** An operations desk: dense tables with tabular figures, one
place for each kind of action, and a way to any object without hunting. A
desk at 1440; one thumb at 390.

**Structure.** A left rail holds every component and its places; no top bar.
Above each page a *trail* names every level above it, derived from the URL
and the `AdminUrlMixin` models, so deployment components get one free
(enrolment: year › class › enrolment). *Jump* (`/`, Ctrl+K or the rail)
searches names across every model a person may change, plus the menu; it is a
GET page, so it works without scripts. Tournament Control gains a page:
seasons in progress with their last and next match days. On a phone the rail
is a drawer and a bottom bar holds Menu, Up, Save and Jump.

**Page types.** *Edit*: kind, name and actions in the head; tabs for the form
and each related list, with counts (chips on a phone); Save and Cancel in one
bar at the top that stays in view (⌘S saves). *Lists*: one table style,
sortable headers, a filter in tabs; row actions at the row's end, its own
buttons first, the rest in a menu; deletes and undos confirm in a dialog and
return to their tab. *Choosing*: a long or multiple select opens a dialog
with search. *Bulk*: "Add several" asks how many, then a sheet of rows; every add page offers "Save and add another".
*Match day*: results are one table per kick-off with both scores side by
side; Allocate, Washout and Live stream share it; the season's Schedule tab
shows results still due; divisions have a Ladder tab. *Print pages* share the
system, self-hosted.

**Type and colour.** Plex Sans and Plex Mono (SIL OFL, self-hosted); Plex
digits are tabular. Colours derive from the five brand properties in OKLCH:
neutrals take the primary's hue; links and focus clamp it to L ≤ 0.47; a
brand fill is pushed out of the 0.5–0.7 band and given dark or light ink by
its lightness, so sherbet's yellow keeps dark text.

**Migration note.** `django-bootstrap3` and `django-gravatar2` are no longer
required (still listing them is harmless). `tab-links` takes
`<a role="tab">`s: include `touchtechnology/admin/_tab.html` with `pane` and
`label`; `tab-panes` takes `<section class="pane" role="tabpanel"
id="…-tab">`. New blocks: `page-kind`, `page-title`, `page-actions`,
`form-actions`. List includes keep their blocks; `row-buttons-items` are
`<li>`s in a menu (a link, or `<button form="console-post" formaction=…>`);
`row-buttons-extra` is on every list. `{% load console %}` gives
`{% icon %}`. A component appears in trails with `index_page = True`.
`TOUCHTECHNOLOGY_HTMX_ADMIN_TABS` still fetches each related pane through
`?_htmx_tab=` when first shown; its tests were rewritten to this markup.

**Proposals.** A pool field on the team form; a default points formula for
bulk-made divisions; Leaflet self-hosted by the common location widget.

**Rough edges.** Without scripts a delete posts without asking; full-page
captures show the phone's bottom bar mid-page; the map loads Leaflet and
tiles from their hosts; no club association form is linked yet.
