from django.conf import settings
from django.core.checks import Error, register

HTMX_MIDDLEWARE = "django_htmx.middleware.HtmxMiddleware"


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
