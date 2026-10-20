"""Run a harness command: ``python -m harness seed|pages``.

The checkout's own ``.venv`` runs this with the environment ``harness_env``
exports (``DJANGO_SETTINGS_MODULE``, ``DATABASE_URL`` and the rest).
"""

import os
import sys

import django
from django.utils.module_loading import import_string

from harness.ownership import refusal

COMMANDS = {
    "seed": "harness.seeding.main",
    "pages": "harness.pages.main",
}


def main(argv: list[str]) -> int:
    if len(argv) < 1 or argv[0] not in COMMANDS:
        print("usage: python -m harness %s" % "|".join(COMMANDS), file=sys.stderr)
        return 64
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vitriolic.settings")
    django.setup()
    message = refusal()
    if message:
        print(message, file=sys.stderr)
        return 3
    # The commands are imported only now: they import models, which need
    # django.setup().
    return import_string(COMMANDS[argv[0]])(argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
