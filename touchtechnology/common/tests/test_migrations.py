"""
Guard the library's models against drifting from the migrations it ships.

A project that installs these apps can run ``makemigrations --check`` as a
safety net, but only if the library's own models already agree with the
library's own migrations. When they do not, the check is never clean and a
plain ``makemigrations`` proposes migrations that must never be committed, such
as an ``AlterField`` that converts every primary key to ``bigint``.

The test project sets ``DEFAULT_AUTO_FIELD`` to ``BigAutoField`` while the
library's migrations create ``AutoField`` primary keys, so these tests catch
models that rely on the project default instead of pinning their own.
"""

from io import StringIO

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from test_plus import TestCase

AUTO_FIELD = "django.db.models.AutoField"

# Every app the library ships, whether or not it has models.
LIBRARY_APPS = (
    "touchtechnology.common",
    "touchtechnology.admin",
    "touchtechnology.content",
    "touchtechnology.news",
    "tournamentcontrol.competition",
)

# The apps that have migrations to compare with: the library's own, plus the
# enrolment app that the test project uses to exercise the library.
MIGRATED_APPS = (
    "touchtechnology.common",
    "touchtechnology.content",
    "touchtechnology.news",
    "tournamentcontrol.competition",
    "enrolment",
)


class MigrationDriftTests(TestCase):

    def test_project_default_differs_from_library_migrations(self):
        """
        The drift tests only mean something while the test project's default
        primary key type is not the one the library's migrations create.
        """
        self.assertEqual(settings.DEFAULT_AUTO_FIELD, "django.db.models.BigAutoField")

    def test_library_apps_pin_their_primary_key_type(self):
        """
        Each app names its own primary key type rather than inheriting the
        project's ``DEFAULT_AUTO_FIELD``, so models match their migrations
        whatever the consuming project sets.
        """
        for name in LIBRARY_APPS:
            with self.subTest(app=name):
                self.assertEqual(
                    apps.get_containing_app_config(name).default_auto_field,
                    AUTO_FIELD,
                )

    def test_makemigrations_check_is_clean(self):
        """
        ``makemigrations --check`` has nothing to write for any migrated app.

        When it does, the failure shows the migration that would be written.
        """
        for name in MIGRATED_APPS:
            label = apps.get_containing_app_config(name).label
            with self.subTest(app=name):
                out = StringIO()
                status = 0
                try:
                    call_command(
                        "makemigrations",
                        label,
                        check=True,
                        dry_run=True,
                        interactive=False,
                        verbosity=3,
                        stdout=out,
                    )
                except SystemExit as exc:
                    status = exc.code
                self.assertEqual(
                    status,
                    0,
                    "makemigrations proposes changes:\n%s" % out.getvalue(),
                )
                self.assertEqual(
                    out.getvalue(), "No changes detected in app '%s'\n" % label
                )
