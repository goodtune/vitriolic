"""
Guard the translation catalogues the library ships.

Only the ``.po`` catalogues are committed; the build compiles the ``.mo`` files
Django reads (see ``setup.py`` and ``docs/translations.md``). So a catalogue
that no longer compiles, or a build that stopped compiling them, would leave
every string in English without anything failing.
"""

import re
from importlib import import_module
from pathlib import Path

from django.utils import translation
from test_plus import TestCase

LOCALES = ("de", "fr", "ja")
APPS = (
    "touchtechnology.admin",
    "touchtechnology.common",
    "touchtechnology.content",
    "touchtechnology.news",
    "tournamentcontrol.competition",
)

# A live entry marked fuzzy; an obsolete one (``#~``) is not looked at.
FUZZY = re.compile(r"^#, .*\bfuzzy\b.*\n(?:#[:|.,] ?.*\n)*msgid ", re.MULTILINE)


def catalogues():
    for name in APPS:
        (app,) = import_module(name).__path__
        for locale in LOCALES:
            yield Path(app) / "locale" / locale / "LC_MESSAGES" / "django.po"


class CatalogueTests(TestCase):
    def test_every_app_has_every_locale_compiled(self):
        for po in catalogues():
            with self.subTest(str(po)):
                self.assertEqual(
                    (po.is_file(), po.with_suffix(".mo").is_file()), (True, True)
                )

    def test_no_entry_is_left_fuzzy(self):
        # Django does not serve a fuzzy entry, so one left behind is a
        # translation that silently stopped being used.
        for po in catalogues():
            with self.subTest(str(po)):
                self.assertEqual(FUZZY.findall(po.read_text(encoding="utf-8")), [])

    def test_compiled_catalogue_is_served(self):
        with translation.override("fr"):
            self.assertEqual(
                translation.gettext("Your {models} have been created."),
                "Vos {models} ont été créés.",
            )
