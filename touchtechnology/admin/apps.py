from django.apps import AppConfig, apps
from django.conf import settings
from django.core import checks
from django.utils.module_loading import import_string
from first import first


class AdminConfig(AppConfig):
    default_site = "touchtechnology.admin.sites.admin.AdminSite"
    name = "touchtechnology.admin"
    label = "touchtechnology_name"

    def ready(self):
        from touchtechnology.admin.sites import site
        from touchtechnology.admin.sites.auth import UsersGroups
        from touchtechnology.admin.sites.settings import Settings

        site.register(UsersGroups)
        site.register(Settings)


@checks.register("config")
def touchtechnology_assumptions(app_configs, **kwargs):
    """
    When building a touchtechnology.admin driven piece of functionality, we
    make plenty of opinionated assumptions about what will be happening. So we
    don't shoot ourselves in the foot too often, these checks should be run to
    ensure we are following our conventions.
    """
    if app_configs is None:
        app_configs = apps.get_app_configs()

    INSTALLED_APPS = [config.name for config in app_configs]

    errors = []

    # determine if we are running a multi-tenanted installation or not
    MULTITENANT = "tenant_schemas" in INSTALLED_APPS
    SITES = "django.contrib.sites" in INSTALLED_APPS

    if not MULTITENANT and not SITES:
        errors.append(
            checks.Critical(
                "touchtechnology.admin requires either 'django-tenant-schemas' or "
                "'django.contrib.sites' to be in INSTALLED_APPS",
                hint="Add either 'tenant_schemas' or 'django.contrib.sites' to "
                "INSTALLED_APPS",
            )
        )

    # ensure appropriate tenant/site middleware is first loaded
    try:
        first_middleware = first(settings.MIDDLEWARE)
    except (AttributeError, TypeError):
        first_middleware = first(settings.MIDDLEWARE_CLASSES)

    if MULTITENANT:
        TenantMiddleware = import_string("tenant_schemas.middleware.TenantMiddleware")
        FirstMiddleware = import_string(first_middleware)
        if not issubclass(FirstMiddleware, TenantMiddleware):
            errors.append(
                checks.Critical(
                    "touchtechnology.admin requires a 'django-tenant-schemas' "
                    "middleware to be listed first.",
                    hint=None,
                )
            )
    elif SITES:
        if first_middleware not in (
            "django.contrib.sites.middleware.CurrentSiteMiddleware",
        ):
            errors.append(
                checks.Critical(
                    "touchtechnology.admin requires "
                    "'django.contrib.sites.middleware.CurrentSiteMiddleware' to "
                    "be listed first.",
                    hint=None,
                )
            )
    else:
        errors.append(
            checks.Warning(
                "Make sure the appropriate middleware is listed first.", hint=None,
            )
        )

    REQUIRED_APPS = {
        "bootstrap3": "django-bootstrap3",
        "django_gravatar": "django-gravatar2",
    }

    for app, package in REQUIRED_APPS.items():
        if app not in INSTALLED_APPS:
            errors.append(
                checks.Critical(
                    "touchtechnology.admin requires {}".format(package),
                    hint='Add "{}" to INSTALLED_APPS'.format(app),
                )
            )

    return errors
