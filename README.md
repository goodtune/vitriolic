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

The aim is to support the current Django LTS release plus the feature releases that follow it. I don't work on this
project all the time, so I need it to be as stable as possible for as long as possible.

Django 5.2 is the minimum supported version. As of this release, we target and test against:

| Django | Python                 | PostgreSQL | Upstream support ends |
|--------|------------------------|------------|-----------------------|
| 5.2    | 3.11, 3.12, 3.13, 3.14 | 14+        | April 2028 (LTS)      |
| 6.0    | 3.12, 3.13, 3.14       | 14+        | April 2027            |
| 6.1    | 3.12, 3.13, 3.14       | 15+        | December 2027         |

The test suite runs against PostgreSQL 15, the oldest release supported by every Django version above.

## Settings the competition sites need

Some pages load template tag libraries that your project has to install. A page whose library is
missing fails when it renders, with a `TemplateSyntaxError`. `manage.py check` reports the gap at
start up, with the lines to add, for each site that your URLconf mounts:

| Site | Needs | Check |
|------|-------|-------|
| `CompOpsSite` | On Django 5.2 only: `template_partials` in `INSTALLED_APPS`, its tags in the template `builtins` and its loader around your template loaders. [The settings in full][compops-partials]. | `tournamentcontrol.competition.E002` (builtins), `E003` (loaders); `CompOpsSite()` itself refuses to mount without the app |
| `TournamentCalculatorSite` | `"mathfilters"` in `INSTALLED_APPS`. | `tournamentcontrol.competition.E004` |
| `CompetitionSite` | `"embed_video"` in `INSTALLED_APPS`, for the match video page. | `tournamentcontrol.competition.W001` (a warning) |

`pip install vitriolic[competition]` installs `django-mathfilters` and `django-embed-video`, but you add them
to `INSTALLED_APPS` yourself. A site is found by its app name (`compops`, `calculator` and `competition`), so a
site that you mount under another `app_name` is not checked.

[compops-partials]: https://github.com/goodtune/vitriolic/blob/main/docs/compops.md#template-partials-on-django-52

[wiktionary word of the day]: https://en.wiktionary.org/wiki/Wiktionary:Word_of_the_day
