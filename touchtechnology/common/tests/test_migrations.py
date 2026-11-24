"""
Guard the library's models against drifting from the migrations it ships.

A project that installs these apps can run ``makemigrations --check`` as a
safety net, but only if the library's own models already agree with the
library's own migrations. When they do not, the check is never clean and a
plain ``makemigrations`` proposes migrations that must never be committed, such
as an ``AlterField`` that converts every primary key to ``bigint``.
"""

from io import StringIO

from django.conf import settings
from django.core.management import call_command
from test_plus import TestCase


class MigrationDriftTests(TestCase):
    # A failure shows the whole migration that would be written.
    maxDiff = None

    def test_project_default_differs_from_library_migrations(self):
        """
        The test project's primary key type is not the one the migrations create.

        The library's migrations create ``AutoField`` primary keys. While the
        test project defaults to something else, an app that does not pin its
        own primary key type is reported as drift by the test below.
        """
        self.assertEqual(settings.DEFAULT_AUTO_FIELD, "django.db.models.BigAutoField")

    def test_makemigrations_has_nothing_to_write(self):
        """
        ``makemigrations --dry-run`` finds no change in any installed app.

        It is the same question as ``makemigrations --check``, answered from the
        output so that a failure shows the migration that would be written.
        """
        out = StringIO()

        call_command(
            "makemigrations",
            dry_run=True,
            interactive=False,
            verbosity=3,
            stdout=out,
        )

        self.assertEqual(out.getvalue(), "No changes detected\n")
