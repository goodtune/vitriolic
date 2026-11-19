"""
Compile the translation catalogues when the package is built.

The ``.po`` catalogues are the source and the ``.mo`` files Django reads are
made from them, so only the ``.po`` files are committed. The build writes each
``.mo`` beside its ``.po`` before the package's files are gathered, which puts
them in the wheel and, for an editable install, in the working tree.

Babel compiles them, so that a build needs no GNU gettext. Like ``msgfmt``, it
leaves out the entries marked ``fuzzy``.
"""

from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).parent
PACKAGES = ("touchtechnology", "tournamentcontrol")


def compile_catalogues():
    for package in PACKAGES:
        for po in sorted((ROOT / package).glob("*/locale/*/LC_MESSAGES/*.po")):
            with po.open("rb") as source:
                catalogue = read_po(source)
            with po.with_suffix(".mo").open("wb") as compiled:
                write_mo(compiled, catalogue)


class BuildPyWithCatalogues(build_py):
    def run(self):
        compile_catalogues()
        super().run()


setup(cmdclass={"build_py": BuildPyWithCatalogues})
