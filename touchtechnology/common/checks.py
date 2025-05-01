from django.conf import settings
from django.core.checks import Error, register


@register()
def check_use_tz_enabled(app_configs, **kwargs):
    """
    Ensure that USE_TZ is turned on.
    """
    errors = []

    if not settings.USE_TZ:
        errors.append(
            Error(
                "USE_TZ must be set to True",
                hint="Set USE_TZ = True in your settings file.",
                id="touchtechnology.common.E001",
            )
        )

    return errors
