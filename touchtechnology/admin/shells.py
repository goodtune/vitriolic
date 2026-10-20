"""
The shells the admin can wear.

A shell is a complete presentation of the admin: its templates, its styles and
scripts, its icons and the template tag library that draws them. The Python
that drives the admin (the components, the explorer, the set-up checklists) is
the same whichever shell is chosen. A deployment chooses one when it builds its
site::

    from touchtechnology.admin.sites import AdminSite

    site = AdminSite(name="admin", shell="explorer")

``"workbook"`` is the default.

Every template a shell ships lives in a directory of its own, next to the
neutral path a deployment may use to override it (see
``AdminComponentMixin._template_path``): the shell's directory is tried first
at each level, then the neutral path at the same level. So a deployment that
overrides ``tournamentcontrol/competition/admin/season/edit.html`` wins over
the shell's page for a season, but not over the shell's page for anything more
general.
"""

import os.path
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from django.core.exceptions import ImproperlyConfigured

#: The directory, under a component's template base, of the pages of every shell.
TEMPLATE_ROOT = "touchtechnology/admin"
STATIC_ROOT = "touchtechnology/admin"

#: The icons Workbook draws from its sprite: one for each component's folder,
#: by the component's ``app_name``, and one for the objects of each model, by
#: the model's name.
WORKBOOK_ICONS = MappingProxyType(
    {
        "components": MappingProxyType(
            {
                "competition": "trophy",
                "content": "file-text",
                "news": "newspaper",
                "auth": "users",
                "enrolment": "graduation-cap",
                "settings": "settings",
            }
        ),
        "component": "layout-grid",
        "models": MappingProxyType(
            {
                "competition": "trophy",
                "season": "calendar",
                "division": "layers",
                "stage": "git-merge",
                "stagegroup": "users-round",
                "team": "shield",
                "undecidedteam": "circle-dashed",
                "venue": "map-pin",
                "ground": "map",
                "match": "goal",
                "club": "flag",
                "person": "user",
                "drawformat": "list-ordered",
                "user": "user",
                "group": "users",
                "article": "newspaper",
                "category": "tag",
                "schoolyear": "school",
                "grade": "award",
                "classgroup": "users-round",
                "student": "user",
                "enrolment": "notebook-pen",
                "teacher": "user",
                "assessment": "clipboard-list",
                "attendancerecord": "list-checks",
                "reportcard": "book-marked",
                "score": "star",
            }
        ),
        # Workbook has an icon for every kind of object; one it does not know
        # gets this.
        "model": "file",
        # A section of a component's menu is drawn with its model's icon.
        "section": "model",
        "item": "file",
        "kinds": MappingProxyType({"page": "file"}),
        "more": "ellipsis",
        "folder": "folder",
    }
)

#: The icons Explorer draws from its sprite. Its sprite is named after the
#: models, so an object is drawn with an icon of its model's name; a
#: section uses the icon its component's menu names for it.
EXPLORER_ICONS = MappingProxyType(
    {
        "components": MappingProxyType(
            {
                "competition": "competition",
                "content": "sitemap",
                "news": "article",
                "auth": "group",
                "settings": "settings",
            }
        ),
        "component": "component",
        "models": MappingProxyType({}),
        "model": None,
        "section": "menu",
        "item": "item",
        "kinds": MappingProxyType({"page": "page"}),
        "more": "more",
        "folder": "folder",
    }
)


@dataclass(frozen=True)
class Shell:
    """
    One presentation of the admin.

    ``template_dir`` is where the shell's pages are, under ``TEMPLATE_ROOT`` for
    the admin itself and under each component's own template base for the
    components'. ``static_prefix`` is the shell's folder of static files.
    ``tag_library`` is the name of the template tag library its templates load.
    ``index_landing`` says whether a component's index is a landing page of its
    own (``True``) or sends the visitor on to the component's first list.
    ``icons`` is the shell's vocabulary of icon names.
    """

    name: str
    template_dir: str
    static_prefix: str
    tag_library: str
    index_landing: bool
    icons: Mapping

    def template(self, filename):
        """The path of one of the shell's own admin templates."""
        return os.path.join(self.template_dir, filename)

    def static(self, filename):
        """The path of one of the shell's own static files."""
        return os.path.join(self.static_prefix, filename)

    def shelled(self, name):
        """
        The shell's own spelling of the name of an admin template that does not
        name a shell: ``<app>/admin/<path>`` becomes ``<app>/admin/<shell>/<path>``.
        """
        head, admin, tail = name.partition("/admin/")
        if not admin:
            return name
        return "%s/admin/%s/%s" % (head, self.name, tail)

    def names(self, name):
        """Where to look for an admin template: the shell's own, then the neutral."""
        return [self.shelled(name), name]

    @property
    def error_template(self):
        """The page the 403 and 404 handlers extend."""
        return self.template("40x.html")

    @property
    def field_template(self):
        """The template a form field is drawn with."""
        return self.template("templatetags/field.html")

    @property
    def print_template(self):
        """The page print layouts (scorecards, reports, grids) extend."""
        return self.template("print.html")

    def component_icon(self, component):
        """The icon of a component's folder in the tree."""
        icons = self.icons
        return getattr(component, "icon", None) or icons["components"].get(
            getattr(component, "app_name", ""), icons["component"]
        )

    def model_icon(self, model):
        """The icon of the objects of a model."""
        icons = self.icons
        default = icons["model"] or model._meta.model_name
        return icons["models"].get(model._meta.model_name, default)

    def section_icon(self, entry, model):
        """
        The icon of a section of a component's menu: ``entry`` is the tuple
        ``AdminComponent.dropdowns`` gave for it, ``model`` the model its list
        shows (or ``None``).
        """
        icons = self.icons
        if icons["section"] == "model":
            return self.model_icon(model) if model else icons["folder"]
        return (entry[2] if len(entry) > 2 else None) or icons["folder"]


WORKBOOK = Shell(
    name="workbook",
    template_dir=os.path.join(TEMPLATE_ROOT, "workbook"),
    static_prefix=os.path.join(STATIC_ROOT, "workbook"),
    tag_library="admin_workbook",
    index_landing=True,
    icons=WORKBOOK_ICONS,
)

EXPLORER = Shell(
    name="explorer",
    template_dir=os.path.join(TEMPLATE_ROOT, "explorer"),
    static_prefix=os.path.join(STATIC_ROOT, "explorer"),
    tag_library="admin_explorer",
    index_landing=False,
    icons=EXPLORER_ICONS,
)

SHELLS = MappingProxyType({shell.name: shell for shell in (WORKBOOK, EXPLORER)})

DEFAULT_SHELL = WORKBOOK.name


def get_shell(name):
    """The shell called ``name``; anything else is a configuration error."""
    try:
        return SHELLS[name]
    except (KeyError, TypeError):
        raise ImproperlyConfigured(
            "Unknown admin shell %r; choose one of %s."
            % (name, ", ".join(repr(known) for known in SHELLS))
        )
