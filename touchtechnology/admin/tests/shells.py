"""
Run test cases under each of the admin's shells.

A test that asserts on the markup or the templates of a page says what the page
is for each shell. Decorate its test case with ``@per_shell``: the case is run
once under every shell (as ``<Name>Workbook`` and ``<Name>Explorer``), the
admin site wearing that shell for the length of each test, and ``self.shell``
is the shell the test is run under::

    @per_shell
    class SignInTests(TestCase):
        def test_sign_in(self):
            self.assertTemplateUsed(response, self.shell.template("login.html"))
            self.assertResponseContains(
                self.by_shell(
                    workbook='<div class="wb-gate-brand">',
                    explorer="<h1>Sign in</h1>",
                ),
            )

Add ``IconMixin`` to such a case for ``self.icon(name)``, the markup of an icon
in the shell the test runs under, or ``ArrowMixin`` for that and
``self.arrow(...)``, the markup of an arrow that moves a row of a list.
"""

import sys

from touchtechnology.admin.shells import SHELLS, get_shell
from touchtechnology.admin.sites import site


def by_shell(**expected):
    """
    The value given for the shell the admin site wears now: for the tests that
    are not run once for each shell (see ``per_shell``) but assert on its markup
    in a place or two, and are run again with ``ADMIN_SHELL`` set.
    """
    return expected[site.shell.name]


class ShellMixin:
    """Puts the admin site in the shell named by ``shell_name`` for each test."""

    shell_name = None

    @property
    def shell(self):
        return get_shell(self.shell_name)

    def by_shell(self, **expected):
        """The value given for the shell the test runs under."""
        return expected[self.shell_name]

    def setUp(self):
        super().setUp()
        previous = site.shell
        site.shell = self.shell_name
        self.addCleanup(setattr, site, "shell", previous)


class IconMixin:
    """The markup of an icon, in the shell a ``per_shell`` test runs under."""

    def icon(self, name):
        css, sprite = self.by_shell(
            workbook=("wb-icon", "workbook/icons.svg"),
            explorer=("icon", "explorer/img/icons.svg"),
        )
        return (
            f'<svg class="{css}" aria-hidden="true" focusable="false">'
            f'<use href="/static/touchtechnology/admin/{sprite}#{name}"></use></svg>'
        )


class ArrowMixin(IconMixin):
    """
    The arrows that move a row of a list up or down, in the shell a
    ``per_shell`` test runs under. Each is a form that posts with the token of
    the page that drew it, so ask after getting that page.
    """

    def arrow(self, action, direction, name):
        """The arrow that posts to ``action`` to move ``name`` ``direction``."""
        csrf = (
            '<input type="hidden" name="csrfmiddlewaretoken" '
            f'value="{self.get_context("csrf_token")}">'
        )
        label = f"Move {direction}"
        icon = self.icon(f"arrow-{direction}")
        return self.by_shell(
            workbook=(
                f'<li><form method="post" action="{action}">{csrf}'
                f'<button type="submit">{icon}{label}</button></form></li>'
            ),
            explorer=(
                f'<form method="post" action="{action}">{csrf}'
                '<button type="submit" class="button quiet icon-only compact" '
                f'title="{label}">{icon}'
                f'<span class="visually-hidden">Move {name} {direction}</span>'
                "</button></form>"
            ),
        )


def per_shell(cls=None, *, shells=None):
    """
    Replace a test case with one for each shell (or each of ``shells``), named
    for the shell and added to the case's module.
    """

    def decorate(cls):
        module = sys.modules[cls.__module__]
        for name in shells or SHELLS:
            shell = get_shell(name)
            generated = type(
                cls.__name__ + shell.name.title(),
                (ShellMixin, cls),
                {"shell_name": shell.name, "__module__": cls.__module__},
            )
            setattr(module, generated.__name__, generated)

    if cls is None:
        return decorate
    return decorate(cls)
