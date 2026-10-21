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
