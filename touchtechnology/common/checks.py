from dataclasses import dataclass
from typing import Any, Optional

from django.conf import settings
from django.core.checks import Error, register


@dataclass
class RequiredSetting:
    """Represents a required constance setting with validation."""
    name: str
    error_id: str
    
    def validate(self, constance_config: dict) -> list:
        """Validate this setting in the constance config."""
        errors = []
        
        if self.name not in constance_config:
            errors.append(
                Error(
                    f"'{self.name}' must be defined in CONSTANCE_CONFIG",
                    hint=f"Add '{self.name}' to CONSTANCE_CONFIG in your settings file.",
                    id=self.error_id,
                )
            )
            return errors
        
        # Validate that the configuration is properly structured
        config_value = constance_config[self.name]
        if not isinstance(config_value, (tuple, list)) or len(config_value) < 2:
            errors.append(
                Error(
                    f"Setting '{self.name}' in CONSTANCE_CONFIG must be a tuple/list with at least (default_value, help_text).",
                    hint=f"Format: '{self.name}': (default_value, 'help text') or (default_value, 'help text', type)",
                    id=self.error_id,
                )
            )
        elif len(config_value) >= 3:
            # If type is specified (3rd element), validate it's a valid type
            specified_type = config_value[2]
            if not isinstance(specified_type, type):
                errors.append(
                    Error(
                        f"Setting '{self.name}' in CONSTANCE_CONFIG has invalid type specification.",
                        hint=f"The third element should be a Python type like str, int, bool, etc.",
                        id=self.error_id,
                    )
                )
        
        return errors


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
        # Early return: can't validate individual settings without CONSTANCE_CONFIG
        return errors

    # Define required constance settings with their error IDs
    required_settings = [
        # Prince PDF Generation
        RequiredSetting("PRINCE_SERVER", "touchtechnology.common.E004"),
        RequiredSetting("PRINCE_BINARY", "touchtechnology.common.E005"),
        RequiredSetting("PRINCE_BASE_URL", "touchtechnology.common.E006"),
        # Touch Technology Common
        RequiredSetting("TOUCHTECHNOLOGY_APP_ROUTING", "touchtechnology.common.E007"),
        RequiredSetting("TOUCHTECHNOLOGY_CURRENCY_ABBREVIATION", "touchtechnology.common.E008"),
        RequiredSetting("TOUCHTECHNOLOGY_CURRENCY_SYMBOL", "touchtechnology.common.E009"),
        RequiredSetting("TOUCHTECHNOLOGY_PAGINATE_BY", "touchtechnology.common.E010"),
        RequiredSetting("TOUCHTECHNOLOGY_PROFILE_FORM_CLASS", "touchtechnology.common.E011"),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_CACHE_DURATION", "touchtechnology.common.E012"),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_EDIT_PARENT", "touchtechnology.common.E013"),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_HTTPS_OPTION", "touchtechnology.common.E014"),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_ROOT", "touchtechnology.common.E015"),
        RequiredSetting("TOUCHTECHNOLOGY_STORAGE_FOLDER", "touchtechnology.common.E016"),
        RequiredSetting("TOUCHTECHNOLOGY_STORAGE_URL", "touchtechnology.common.E017"),
        # Touch Technology Content
        RequiredSetting("TOUCHTECHNOLOGY_NODE_CACHE", "touchtechnology.common.E018"),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS", "touchtechnology.common.E019"),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES", "touchtechnology.common.E020"),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE", "touchtechnology.common.E021"),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER", "touchtechnology.common.E022"),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX", "touchtechnology.common.E023"),
        RequiredSetting("TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC", "touchtechnology.common.E024"),
        # Touch Technology News
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS", "touchtechnology.common.E025"),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS", "touchtechnology.common.E026"),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_PAGINATE_BY", "touchtechnology.common.E027"),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS", "touchtechnology.common.E028"),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS", "touchtechnology.common.E029"),
        # Tournament Control Competition
        RequiredSetting("TOURNAMENTCONTROL_COMPETITION_VIDEOS_ARRAY_SIZE", "touchtechnology.common.E030"),
        RequiredSetting("TOURNAMENTCONTROL_SCORECARD_PDF_WAIT", "touchtechnology.common.E031"),
        RequiredSetting("TOURNAMENTCONTROL_ASYNC_PDF_GRID", "touchtechnology.common.E032"),
        # Other
        RequiredSetting("FROALA_EDITOR_OPTIONS", "touchtechnology.common.E033"),
        RequiredSetting("GOOGLE_ANALYTICS", "touchtechnology.common.E034"),
        RequiredSetting("ANONYMOUS_USER_ID", "touchtechnology.common.E035"),
    ]

    constance_config = getattr(settings, "CONSTANCE_CONFIG", {})
    for required_setting in required_settings:
        errors.extend(required_setting.validate(constance_config))

    return errors

