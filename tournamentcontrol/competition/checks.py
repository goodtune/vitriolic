import django
from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.urls import get_resolver

HTMX_MIDDLEWARE = "django_htmx.middleware.HtmxMiddleware"

# The app name each site is mounted under, unless the project gives it another.
OPS_APP_NAME = "compops"
COMPETITION_APP_NAME = "competition"
CALCULATOR_APP_NAME = "calculator"

DJANGO_TEMPLATES = "django.template.backends.django.DjangoTemplates"
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


def template_partials_problems():
    """
    Before Django 6.0 the ops site's templates need the partials from
    django-template-partials: its tags as builtins, and its loader around the
    project's own loaders. Django 6.0 has both built in. The app itself needs
    no check here, as ``CompOpsSite()`` refuses to mount without it.
    """
    if django.VERSION >= (6, 0):
        return []

    options = next(
        (
            config.get("OPTIONS", {})
            for config in settings.TEMPLATES
            if config.get("BACKEND") == DJANGO_TEMPLATES
        ),
        None,
    )
    if options is None:
        return []

    problems = []

    if PARTIALS_BUILTIN not in options.get("builtins", []):
        problems.append(
            Error(
                f'CompOpsSite is mounted, but "{PARTIALS_BUILTIN}" is not in the '
                "template builtins. Its templates use {% partialdef %} and "
                "{% partial %} without {% load %}.",
                hint=f'Add "{PARTIALS_BUILTIN}" to "builtins" in the OPTIONS of '
                "the DjangoTemplates entry in TEMPLATES, for example "
                f'"builtins": ["{PARTIALS_BUILTIN}"].',
                id="tournamentcontrol.competition.E002",
            )
        )

    # The partials loader must be the first loader: the app looks there before
    # it replaces the loaders, and it strips "#name" off a template name for
    # the loaders it wraps, so the others never see the name of a partial.
    first = (options.get("loaders") or [()])[0]
    if tuple(first[:1]) != (PARTIALS_LOADER,):
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
                id="tournamentcontrol.competition.E003",
            )
        )

    return problems


@register(Tags.templates, "config")
def check_site_requirements(app_configs, **kwargs):
    """
    Report the apps and template settings that a mounted site needs, where
    leaving them out would fail at render time with a ``TemplateSyntaxError``.

    A site is mounted when its app name is one of the URLconf's, which is what
    Django's own URL resolver keeps. So a project that does not mount a site
    is not asked for what it needs. A site mounted under another app name, or
    from a content node (a database row, which a check must not read), is not
    seen.
    """
    if not getattr(settings, "ROOT_URLCONF", None):
        return []

    mounted = get_resolver().app_dict

    problems = []

    if OPS_APP_NAME in mounted:
        problems.extend(template_partials_problems())

    if CALCULATOR_APP_NAME in mounted and not apps.is_installed("mathfilters"):
        problems.append(
            Error(
                "TournamentCalculatorSite is mounted, but 'mathfilters' is not in "
                "INSTALLED_APPS. Its pages load the mathfilters tag library.",
                hint='Add "mathfilters" to INSTALLED_APPS (django-mathfilters is '
                "installed with vitriolic[competition]).",
                id="tournamentcontrol.competition.E004",
            )
        )

    # Only a warning: the rest of the competition site works without it.
    if COMPETITION_APP_NAME in mounted and not apps.is_installed("embed_video"):
        problems.append(
            Warning(
                "CompetitionSite is mounted, but 'embed_video' is not in "
                "INSTALLED_APPS, so its match video page cannot render.",
                hint='Add "embed_video" to INSTALLED_APPS (django-embed-video is '
                "installed with vitriolic[competition]).",
                id="tournamentcontrol.competition.W001",
            )
        )

    return problems
