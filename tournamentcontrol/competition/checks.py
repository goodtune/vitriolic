import logging

import django
from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.urls import URLResolver, get_resolver

from touchtechnology.common.sites import Application

logger = logging.getLogger(__name__)

HTMX_MIDDLEWARE = "django_htmx.middleware.HtmxMiddleware"

# The sites are named, not imported: the ops site needs the "async" extra, and
# a project that does not mount it must not need that to start.
COMPOPS_SITE = "tournamentcontrol.competition.compops.sites.CompOpsSite"
COMPETITION_SITE = "tournamentcontrol.competition.sites.CompetitionSite"
CALCULATOR_SITE = "tournamentcontrol.competition.sites.TournamentCalculatorSite"

DJANGO_TEMPLATES = "django.template.backends.django.DjangoTemplates"
TEMPLATE_PARTIALS = "template_partials"
PARTIALS_BUILTIN = "template_partials.templatetags.partials"
PARTIALS_LOADER = "template_partials.loader.Loader"


@register()
def check_htmx_middleware(app_configs, **kwargs):
    """
    Ensure the django-htmx middleware is installed.

    The competition views rely on ``request.htmx`` to decide when to
    serve template fragments instead of full pages.
    """
    errors = []

    if HTMX_MIDDLEWARE not in settings.MIDDLEWARE:
        errors.append(
            Error(
                "django-htmx middleware is not installed.",
                hint=f'Add "{HTMX_MIDDLEWARE}" to MIDDLEWARE.',
                id="tournamentcontrol.competition.E001",
            )
        )

    return errors


def sites_in(patterns):
    """The ``Application`` instances that own the views in ``patterns``."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from sites_in(pattern.url_patterns)
        else:
            site = getattr(pattern.callback, "__self__", None)
            if isinstance(site, Application):
                yield site


def mounted_sites():
    """
    The dotted paths of the site classes that ``ROOT_URLCONF`` mounts, with
    those of their bases, so that a subclass of a site is a site.

    A site is found by the views it serves, so one is mounted however the
    project names it. A site mounted from a content node is not found: nodes
    are rows in the database, which a check must not read.
    """
    if not getattr(settings, "ROOT_URLCONF", None):
        return frozenset()
    try:
        kinds = {type(site) for site in sites_in(get_resolver().url_patterns)}
    except Exception as exc:
        # The URL checks run alongside this one and raise the same error.
        logger.debug("The URLconf did not load, so no sites are known: %s", exc)
        return frozenset()
    return frozenset(
        f"{cls.__module__}.{cls.__qualname__}" for kind in kinds for cls in kind.__mro__
    )


def django_templates_options():
    """The ``OPTIONS`` of the first Django template engine, if there is one."""
    for config in settings.TEMPLATES:
        if config.get("BACKEND") == DJANGO_TEMPLATES:
            return config.get("OPTIONS", {})
    return None


def loaders_wrapped(options):
    """
    Whether the engine's first loader is the partials loader. That is the one
    the app looks for before it replaces the loaders, and the only place
    where it can strip ``#name`` off a template name for the loaders it wraps.
    """
    loaders = options.get("loaders")
    if not isinstance(loaders, (list, tuple)) or not loaders:
        return False
    first = loaders[0]
    return isinstance(first, (list, tuple)) and list(first[:1]) == [PARTIALS_LOADER]


def template_partials_problems():
    """
    Before Django 6.0 the ops site's templates need the partials from
    django-template-partials: the app, its tags as builtins, and its loader
    around the project's own loaders. Django 6.0 has all of it built in.
    """
    if django.VERSION >= (6, 0):
        return []

    problems = []

    if not apps.is_installed(TEMPLATE_PARTIALS):
        problems.append(
            Error(
                f"CompOpsSite is mounted, but '{TEMPLATE_PARTIALS}' is not in "
                "INSTALLED_APPS. Before Django 6.0 its templates need "
                "django-template-partials for {% partialdef %} and {% partial %}.",
                hint=f'Add "{TEMPLATE_PARTIALS}" to INSTALLED_APPS. See '
                "docs/compops.md for the template settings that go with it.",
                id="tournamentcontrol.competition.E002",
            )
        )

    options = django_templates_options()
    if options is None:
        return problems

    if PARTIALS_BUILTIN not in options.get("builtins", []):
        problems.append(
            Error(
                f'CompOpsSite is mounted, but "{PARTIALS_BUILTIN}" is not in the '
                "template builtins. Its templates use {% partialdef %} and "
                "{% partial %} without {% load %}.",
                hint=f'Add "{PARTIALS_BUILTIN}" to "builtins" in the OPTIONS of '
                "the DjangoTemplates entry in TEMPLATES, for example "
                f'"builtins": ["{PARTIALS_BUILTIN}"].',
                id="tournamentcontrol.competition.E003",
            )
        )

    if not loaders_wrapped(options):
        problems.append(
            Error(
                "CompOpsSite is mounted, but the template loaders are not wrapped "
                f'in "{PARTIALS_LOADER}". It renders fragments by name (for '
                'example "tournamentcontrol/competition/compops/day.html#results"), '
                "which only that loader can find.",
                hint='Set "loaders" in the OPTIONS of the DjangoTemplates entry in '
                f'TEMPLATES to [("{PARTIALS_LOADER}", [<your loaders>])], listing '
                "the loaders you use now in place of <your loaders>, for example "
                '["django.template.loaders.filesystem.Loader", '
                '"django.template.loaders.app_directories.Loader"]. Remove '
                "APP_DIRS when you set loaders. See docs/compops.md.",
                id="tournamentcontrol.competition.E004",
            )
        )

    return problems


def calculator_problems():
    """The calculator's pages load the ``mathfilters`` tag library."""
    if apps.is_installed("mathfilters"):
        return []
    return [
        Error(
            "TournamentCalculatorSite is mounted, but 'mathfilters' is not in "
            "INSTALLED_APPS. Its pages load the mathfilters tag library.",
            hint='Add "mathfilters" to INSTALLED_APPS (django-mathfilters is '
            "installed with vitriolic[competition]).",
            id="tournamentcontrol.competition.E005",
        )
    ]


def match_video_problems():
    """
    The match video page loads the ``embed_video`` tag library. A warning, as
    the rest of the competition site works without it.
    """
    if apps.is_installed("embed_video"):
        return []
    return [
        Warning(
            "CompetitionSite is mounted, but 'embed_video' is not in "
            "INSTALLED_APPS, so its match video page cannot render.",
            hint='Add "embed_video" to INSTALLED_APPS (django-embed-video is '
            "installed with vitriolic[competition]).",
            id="tournamentcontrol.competition.W001",
        )
    ]


@register(Tags.templates, "config")
def check_site_requirements(app_configs, **kwargs):
    """
    Report the apps and template settings that a mounted site needs, where
    leaving them out would fail at render time with a ``TemplateSyntaxError``.

    Only the sites in the project's URLconf are checked, so a project that
    does not use a site is not asked for what it needs.
    """
    mounted = mounted_sites()

    problems = []
    if COMPOPS_SITE in mounted:
        problems.extend(template_partials_problems())
    if CALCULATOR_SITE in mounted:
        problems.extend(calculator_problems())
    if COMPETITION_SITE in mounted:
        problems.extend(match_video_problems())
    return problems
