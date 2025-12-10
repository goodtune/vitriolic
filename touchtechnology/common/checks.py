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


@register()
def check_constance_installed(app_configs, **kwargs):
    """
    Ensure that django-constance is properly installed and configured.
    """
    errors = []

    # Check if constance is in INSTALLED_APPS
    if "constance" not in settings.INSTALLED_APPS:
        errors.append(
            Error(
                "'constance' must be in INSTALLED_APPS",
                hint="Add 'constance' to your INSTALLED_APPS setting.",
                id="touchtechnology.common.E002",
            )
        )

    # Check if CONSTANCE_CONFIG is defined
    if not hasattr(settings, "CONSTANCE_CONFIG"):
        errors.append(
            Error(
                "CONSTANCE_CONFIG must be defined in settings",
                hint="Add CONSTANCE_CONFIG dictionary to your settings file.",
                id="touchtechnology.common.E003",
            )
        )
        return errors

    # Check for required constance settings
    required_settings = {
        # Prince PDF Generation
        "PRINCE_SERVER": "touchtechnology.common.E004",
        "PRINCE_BINARY": "touchtechnology.common.E005",
        "PRINCE_BASE_URL": "touchtechnology.common.E006",
        # Touch Technology Common
        "TOUCHTECHNOLOGY_APP_ROUTING": "touchtechnology.common.E007",
        "TOUCHTECHNOLOGY_CURRENCY_ABBREVIATION": "touchtechnology.common.E008",
        "TOUCHTECHNOLOGY_CURRENCY_SYMBOL": "touchtechnology.common.E009",
        "TOUCHTECHNOLOGY_PAGINATE_BY": "touchtechnology.common.E010",
        "TOUCHTECHNOLOGY_PROFILE_FORM_CLASS": "touchtechnology.common.E011",
        "TOUCHTECHNOLOGY_SITEMAP_CACHE_DURATION": "touchtechnology.common.E012",
        "TOUCHTECHNOLOGY_SITEMAP_EDIT_PARENT": "touchtechnology.common.E013",
        "TOUCHTECHNOLOGY_SITEMAP_HTTPS_OPTION": "touchtechnology.common.E014",
        "TOUCHTECHNOLOGY_SITEMAP_ROOT": "touchtechnology.common.E015",
        "TOUCHTECHNOLOGY_STORAGE_FOLDER": "touchtechnology.common.E016",
        "TOUCHTECHNOLOGY_STORAGE_URL": "touchtechnology.common.E017",
        # Touch Technology Content
        "TOUCHTECHNOLOGY_NODE_CACHE": "touchtechnology.common.E018",
        "TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS": "touchtechnology.common.E019",
        "TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES": "touchtechnology.common.E020",
        "TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE": "touchtechnology.common.E021",
        "TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER": "touchtechnology.common.E022",
        "TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX": "touchtechnology.common.E023",
        "TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC": "touchtechnology.common.E024",
        # Touch Technology News
        "TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS": "touchtechnology.common.E025",
        "TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS": "touchtechnology.common.E026",
        "TOUCHTECHNOLOGY_NEWS_PAGINATE_BY": "touchtechnology.common.E027",
        "TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS": "touchtechnology.common.E028",
        "TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS": "touchtechnology.common.E029",
        # Tournament Control Competition
        "TOURNAMENTCONTROL_COMPETITION_VIDEOS_ARRAY_SIZE": "touchtechnology.common.E030",
        "TOURNAMENTCONTROL_SCORECARD_PDF_WAIT": "touchtechnology.common.E031",
        "TOURNAMENTCONTROL_ASYNC_PDF_GRID": "touchtechnology.common.E032",
        # Other
        "FROALA_EDITOR_OPTIONS": "touchtechnology.common.E033",
        "GOOGLE_ANALYTICS": "touchtechnology.common.E034",
        "ANONYMOUS_USER_ID": "touchtechnology.common.E035",
    }

    constance_config = getattr(settings, "CONSTANCE_CONFIG", {})
    for setting_name, error_id in required_settings.items():
        if setting_name not in constance_config:
            errors.append(
                Error(
                    f"'{setting_name}' must be defined in CONSTANCE_CONFIG",
                    hint=f"Add '{setting_name}' to CONSTANCE_CONFIG in your settings file.",
                    id=error_id,
                )
            )

    return errors

