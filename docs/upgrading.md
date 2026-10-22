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

- `mvp/list.html`, `mvp/list.inc.html` and `mvp/list.split.inc.html` are now
  `touchtechnology/admin/<shell>/mvp/list.html`, `.../mvp/list.inc.html` and
  `.../mvp/list.split.inc.html`.
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

### Templates that replace a page

A template of yours that *replaces* a page of the admin is a different case.
Where the admin finds a page by searching, a template at the 4.x name still
wins, for either shell. The admin searches the template folders of a component
and then `touchtechnology/admin/`, so `tournamentcontrol/competition/admin/season/edit.html`
in your project is still chosen. This is how the admin finds `list.html`,
`list.inc.html`, `edit.html`, `edit.related.html` and `permissions.html`.

The admin does not search for some pages. It asks for them by name, in the
folder of the shell: the home page (`index.html`), the sign-in page, the HTMX
tab fragments and the `mvp` list pages. A template of yours at the 4.x name of
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
