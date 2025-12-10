# vitriolic

[![PyPi Version](https://img.shields.io/pypi/v/vitriolic.svg)](https://pypi.python.org/pypi/vitriolic)

This project unifies the various subprojects Touch Technology has created over the years that were intended to be
reusable in isolation, but in practice never stood alone for long. The maintenance burden has become too great.

## Origin of the name

I decided to do this on Tuesday 8th November, US Election day 2016. The [wiktionary word of the day] was `vitriolic`
which, given the nature of Donald Trump's campaign to become American President, it seemed like a pretty good fit.

~~As at time of authoring this document I have no idea if he'll win the election.~~

This project will now forever remind me of the day that America shat the bed.

## Supported Django versions

The aim is to only support LTS versions of Django. I don't work on this project all the time, so I need it to be as
stable as possible for as long as possible.

As of this release, we target and test against:
- Django 4.2 and 5.2 (LTS releases) with Python 3.11, 3.12, and 3.13
- Django 5.2 (latest patch releases) with Python 3.14 (when available)
- Django 6.0 with Python 3.12, 3.13, and 3.14 (when available)

**Note**: Testing dimensions for Python 3.14 are configured but will be skipped if the version
is not yet available (`skip_missing_interpreters = true` in tox.ini).

[wiktionary word of the day]: https://en.wiktionary.org/wiki/Wiktionary:Word_of_the_day
