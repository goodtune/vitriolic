import copy
import unittest
from unittest import mock

import django
from django.conf import settings
from django.core import checks
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import get_template, render_to_string
from django.test import modify_settings, override_settings
from template_partials.apps import wrap_loaders
from test_plus import TestCase

PREFIX = "tournamentcontrol.competition."

PARTIALS_BUILTIN = "template_partials.templatetags.partials"
PARTIALS_LOADER = "template_partials.loader.Loader"

FILESYSTEM_LOADER = "django.template.loaders.filesystem.Loader"
APP_DIRECTORIES_LOADER = "django.template.loaders.app_directories.Loader"
CACHED_LOADER = "django.template.loaders.cached.Loader"
DEFAULT_LOADERS = [FILESYSTEM_LOADER, APP_DIRECTORIES_LOADER]

# The library's own settings mount the ops site only; the competition app's
# test URLs mount the competition site and the calculator; the example app
# mounts none of the three.
COMPETITION_URLS = "tournamentcontrol.competition.tests.urls"
NO_URLS = "example_app.urls"

SKIP_FROM_DJANGO_6 = unittest.skipIf(
    django.VERSION >= (6, 0), "Django 6.0 has template partials built in"
)

# Behave as Django 5.2 or as 6.0 does, whichever Django runs the tests.
DJANGO_5 = mock.patch.object(django, "VERSION", (5, 2, 0))
DJANGO_6 = mock.patch.object(django, "VERSION", (6, 0, 0))

E002 = checks.Error(
    'CompOpsSite is mounted, but "template_partials.templatetags.partials" is '
    "not in the template builtins. Its templates use {% partialdef %} and "
    "{% partial %} without {% load %}.",
    hint='Add "template_partials.templatetags.partials" to "builtins" in the '
    "OPTIONS of the DjangoTemplates entry in TEMPLATES, for example "
    '"builtins": ["template_partials.templatetags.partials"].',
    id="tournamentcontrol.competition.E002",
)

E003 = checks.Error(
    "CompOpsSite is mounted, but the template loaders are not wrapped in "
    '"template_partials.loader.Loader". It renders fragments by name (for '
    'example "tournamentcontrol/competition/compops/day.html#results"), which '
    "only that loader can find.",
    hint='Set "loaders" in the OPTIONS of the DjangoTemplates entry in TEMPLATES '
    'to [("template_partials.loader.Loader", [<your loaders>])], listing the '
    "loaders you use now in place of <your loaders>, for example "
    '["django.template.loaders.filesystem.Loader", '
    '"django.template.loaders.app_directories.Loader"]. Remove APP_DIRS when '
    "you set loaders. See docs/compops.md.",
    id="tournamentcontrol.competition.E003",
)

E004 = checks.Error(
    "TournamentCalculatorSite is mounted, but 'mathfilters' is not in "
    "INSTALLED_APPS. Its pages load the mathfilters tag library.",
    hint='Add "mathfilters" to INSTALLED_APPS (django-mathfilters is installed '
    "with vitriolic[competition]).",
    id="tournamentcontrol.competition.E004",
)

W001 = checks.Warning(
    "CompetitionSite is mounted, but 'embed_video' is not in INSTALLED_APPS, so "
    "its match video page cannot render.",
    hint='Add "embed_video" to INSTALLED_APPS (django-embed-video is installed '
    "with vitriolic[competition]).",
    id="tournamentcontrol.competition.W001",
)


def problems(tag="templates"):
    """What the registered checks report with the competition app's prefix."""
    return [
        message
        for message in checks.run_checks(tags=[tag])
        if message.id.startswith(PREFIX)
    ]


def templates(builtins=(), loaders=None, app_dirs=False):
    """
    The project's ``TEMPLATES`` with only the options under test: the
    ``builtins``, the ``loaders`` (left out when ``None``) and ``APP_DIRS``.
    """
    config = copy.deepcopy(settings.TEMPLATES[0])
    config.pop("APP_DIRS", None)
    config["OPTIONS"].pop("loaders", None)
    config["OPTIONS"]["builtins"] = list(builtins)
    if loaders is not None:
        config["OPTIONS"]["loaders"] = loaders
    if app_dirs:
        config["APP_DIRS"] = True
    return [config]


class LibrarySettingsTests(TestCase):
    """The settings the library tests with satisfy every requirement."""

    def test_ops_site_mounted(self):
        self.assertEqual(problems(), [])

    @override_settings(ROOT_URLCONF=COMPETITION_URLS)
    def test_competition_site_and_calculator_mounted(self):
        self.assertEqual(problems(), [])

    def test_config_tag(self):
        self.assertEqual(problems("config"), [])


class TemplatePartialsTests(TestCase):
    """CompOpsSite on Django 5.2 needs the builtins and the loader."""

    wrapped = [(PARTIALS_LOADER, DEFAULT_LOADERS)]

    @override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], wrapped))
    def test_complete_setup_reports_nothing(self):
        with DJANGO_5:
            self.assertEqual(problems(), [])

    @override_settings(TEMPLATES=templates([], wrapped))
    def test_missing_builtin(self):
        with DJANGO_5:
            self.assertEqual(problems(), [E002])

    @override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], DEFAULT_LOADERS))
    def test_project_loaders_not_wrapped(self):
        with DJANGO_5:
            self.assertEqual(problems(), [E003])

    @override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], app_dirs=True))
    def test_app_dirs_project_not_wrapped(self):
        with DJANGO_5:
            self.assertEqual(problems(), [E003])

    @override_settings(TEMPLATES=templates([PARTIALS_BUILTIN]))
    def test_default_loaders_not_wrapped(self):
        with DJANGO_5:
            self.assertEqual(problems(), [E003])

    @override_settings(
        TEMPLATES=templates(
            [PARTIALS_BUILTIN], [(CACHED_LOADER, [(PARTIALS_LOADER, DEFAULT_LOADERS)])]
        )
    )
    def test_loader_must_be_outermost(self):
        with DJANGO_5:
            self.assertEqual(problems(), [E003])

    @override_settings(
        TEMPLATES=templates([PARTIALS_BUILTIN], [[PARTIALS_LOADER, DEFAULT_LOADERS]])
    )
    def test_loader_given_as_a_list(self):
        with DJANGO_5:
            self.assertEqual(problems(), [])

    @override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], []))
    def test_no_loaders_at_all(self):
        with DJANGO_5:
            self.assertEqual(problems(), [E003])

    @override_settings(TEMPLATES=templates())
    def test_everything_missing_is_reported_piece_by_piece(self):
        with DJANGO_5:
            self.assertEqual(problems(), [E002, E003])

    @override_settings(TEMPLATES=templates())
    def test_config_tag(self):
        with DJANGO_5:
            self.assertEqual(problems("config"), [E002, E003])

    @override_settings(TEMPLATES=templates())
    def test_django_6_has_partials_built_in(self):
        with DJANGO_6:
            self.assertEqual(problems(), [])

    @override_settings(TEMPLATES=templates(), ROOT_URLCONF=NO_URLS)
    def test_ops_site_not_mounted(self):
        with DJANGO_5:
            self.assertEqual(problems(), [])

    @override_settings(TEMPLATES=templates(), ROOT_URLCONF=COMPETITION_URLS)
    def test_competition_site_and_calculator_do_not_need_partials(self):
        with DJANGO_5:
            self.assertEqual(problems(), [])

    @override_settings(
        TEMPLATES=[{"BACKEND": "django.template.backends.dummy.TemplateStrings"}]
    )
    def test_no_django_templates_engine_to_inspect(self):
        with DJANGO_5:
            self.assertEqual(problems(), [])


@SKIP_FROM_DJANGO_6
class TemplatePartialsSetupTests(TestCase):
    """What the checks demand is what makes a partial render by name."""

    page = "{% partialdef greeting %}hello{% endpartialdef %}{% partial greeting %}"

    def own(self, wrapped):
        loaders = [("django.template.loaders.locmem.Loader", {"page.html": self.page})]
        if wrapped:
            return [(PARTIALS_LOADER, loaders)]
        return loaders

    def test_project_loaders_wrapped_as_documented(self):
        with override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], self.own(True))):
            self.assertEqual(render_to_string("page.html#greeting"), "hello")
            self.assertEqual(problems(), [])

    def test_project_loaders_left_unwrapped(self):
        with override_settings(
            TEMPLATES=templates([PARTIALS_BUILTIN], self.own(False))
        ):
            with self.assertRaises(TemplateDoesNotExist):
                render_to_string("page.html#greeting")
            self.assertEqual(problems(), [E003])

    def test_builtin_left_out(self):
        with override_settings(TEMPLATES=templates([], self.own(True))):
            with self.assertRaisesMessage(
                TemplateSyntaxError,
                "Invalid block tag on line 1: 'partialdef'. Did you forget to "
                "register or load this tag?",
            ):
                render_to_string("page.html")
            self.assertEqual(problems(), [E002])

    def test_project_loaders_wrapped_with_the_cached_loader_inside(self):
        loaders = [(PARTIALS_LOADER, [(CACHED_LOADER, self.own(False))])]
        with override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], loaders)):
            self.assertEqual(render_to_string("page.html#greeting"), "hello")
            self.assertEqual(problems(), [])

    def test_cached_loader_around_the_partials_loader(self):
        loaders = [(CACHED_LOADER, self.own(True))]
        with override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], loaders)):
            with self.assertRaises(TemplateDoesNotExist):
                render_to_string("page.html#greeting")
            self.assertEqual(problems(), [E003])

    def test_app_installed_for_a_project_with_app_dirs(self):
        with override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], app_dirs=True)):
            # The app does this for the project when it is ready.
            wrap_loaders("django")
            self.assertEqual(
                get_template(
                    "tournamentcontrol/competition/compops/booth.html#lamp"
                ).template.name,
                "lamp",
            )
            self.assertEqual(problems(), [])

    def test_app_replaces_project_loaders_that_are_not_wrapped(self):
        with override_settings(
            TEMPLATES=templates([PARTIALS_BUILTIN], self.own(False))
        ):
            wrap_loaders("django")
            with self.assertRaises(TemplateDoesNotExist):
                render_to_string("page.html")

    def test_app_keeps_project_loaders_that_are_wrapped(self):
        with override_settings(TEMPLATES=templates([PARTIALS_BUILTIN], self.own(True))):
            wrap_loaders("django")
            self.assertEqual(render_to_string("page.html#greeting"), "hello")


class MathfiltersTests(TestCase):
    """The calculator's pages load the mathfilters tag library."""

    @override_settings(ROOT_URLCONF=COMPETITION_URLS)
    @modify_settings(INSTALLED_APPS={"remove": ["mathfilters"]})
    def test_missing_app(self):
        self.assertEqual(problems(), [E004])

    @modify_settings(INSTALLED_APPS={"remove": ["mathfilters"]})
    def test_calculator_not_mounted(self):
        self.assertEqual(problems(), [])


class EmbedVideoTests(TestCase):
    """The match video page loads the embed_video tag library."""

    @override_settings(ROOT_URLCONF=COMPETITION_URLS)
    @modify_settings(INSTALLED_APPS={"remove": ["embed_video"]})
    def test_missing_app(self):
        self.assertEqual(problems(), [W001])

    @modify_settings(INSTALLED_APPS={"remove": ["embed_video"]})
    def test_competition_site_not_mounted(self):
        self.assertEqual(problems(), [])

    @override_settings(ROOT_URLCONF=COMPETITION_URLS)
    @modify_settings(INSTALLED_APPS={"remove": ["embed_video", "mathfilters"]})
    def test_both_missing(self):
        self.assertEqual(problems(), [E004, W001])


class NothingMountedTests(TestCase):
    """A project that mounts none of the sites is never asked for anything."""

    @override_settings(TEMPLATES=templates(), ROOT_URLCONF=NO_URLS)
    @modify_settings(INSTALLED_APPS={"remove": ["embed_video", "mathfilters"]})
    def test_nothing_reported(self):
        with DJANGO_5:
            self.assertEqual(problems(), [])
