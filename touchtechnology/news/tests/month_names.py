"""
Build the month name table from Babel's locale data.

``touchtechnology.news.month_names.MONTH_NUMBERS`` is this table, written out
once so that the news views do not need Babel (and 34 locales' worth of data)
at request time. ``MonthNamesTest`` fails if the two drift apart, for example
when a newer Babel ships revised month names.

To regenerate the module, run this with ``-m`` and write the output over
``touchtechnology/news/month_names.py``::

    python -m touchtechnology.news.tests.month_names
"""

import pprint

from babel import Locale
from babel.dates import get_month_names

# Locales whose month names are accepted in the URL, in precedence order: where
# two locales use the same name for different months the later one wins.
LOCALES = [
    "en",
    "fr",
    "de",
    "es",
    "it",
    "pt",
    "zh",
    "ja",
    "ko",
    "ru",
    "nl",
    "da",
    "sv",
    "no",
    "fi",
    "pl",
    "cs",
    "hu",
    "ro",
    "bg",
    "hr",
    "sl",
    "sk",
    "lt",
    "lv",
    "et",
    "ar",
    "he",
    "hi",
    "th",
    "vi",
    "id",
    "ms",
]

HEADER = '''\
"""
Month names, in the languages the news URLs may use, mapped to month numbers.

Generated from Babel's locale data by ``touchtechnology.news.tests.month_names``;
do not edit by hand. Names are lowercase, and both the full and the abbreviated
forms are present.
"""

MONTH_NUMBERS = '''


def build_month_numbers():
    month_numbers = {}

    for locale_code in LOCALES:
        locale = Locale(locale_code)

        for month_number, name in get_month_names("wide", locale=locale).items():
            if name:
                month_numbers[name.lower()] = month_number

        for month_number, name in get_month_names("abbreviated", locale=locale).items():
            if name and name.lower() not in month_numbers:
                month_numbers[name.lower()] = month_number

    return dict(sorted(month_numbers.items()))


def render_module():
    return (
        HEADER
        + pprint.pformat(build_month_numbers(), width=88, sort_dicts=False)
        + "\n"
    )


if __name__ == "__main__":
    print(render_module(), end="")
