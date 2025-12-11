from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.checks import Error, register


@dataclass
class ConstanceConfigValue:
    """Represents the value structure in CONSTANCE_CONFIG."""
    default_value: Any
    help_text: str
    specified_type: type | None = None
    
    @classmethod
    def from_config(cls, config_tuple):
        """Create a ConstanceConfigValue from a config tuple.
        
        Uses Pythonic approach - try to unpack and handle exceptions.
        """
        try:
            return cls(*config_tuple)
        except (TypeError, ValueError):
            # TypeError: not a sequence, or wrong number of arguments
            # ValueError: can also occur during unpacking
            return None


@dataclass
class RequiredSetting:
    """Represents a required constance setting with validation."""
    name: str
    error_id: str
    expected_type: type
    
    def validate(self) -> list:
        """Validate this setting in the constance config."""
        errors = []
        constance_config = settings.CONSTANCE_CONFIG
        
        if self.name not in constance_config:
            errors.append(
                Error(
                    f"'{self.name}' must be defined in CONSTANCE_CONFIG",
                    hint=f"Add '{self.name}' to CONSTANCE_CONFIG in your settings file.",
                    id=self.error_id,
                )
            )
            return errors
        
        # Parse the configuration value
        config_value = ConstanceConfigValue.from_config(constance_config[self.name])
        
        if config_value is None:
            errors.append(
                Error(
                    f"Setting '{self.name}' in CONSTANCE_CONFIG must be a tuple/list with at least (default_value, help_text).",
                    hint=f"Format: '{self.name}': (default_value, 'help text') or (default_value, 'help text', type)",
                    id=self.error_id,
                )
            )
            return errors
        
        # Validate type specification if present
        if config_value.specified_type is not None:
            if not isinstance(config_value.specified_type, type):
                errors.append(
                    Error(
                        f"Setting '{self.name}' in CONSTANCE_CONFIG has invalid type specification.",
                        hint=f"The third element should be a Python type like str, int, bool, etc.",
                        id=self.error_id,
                    )
                )
            elif config_value.specified_type != self.expected_type:
                errors.append(
                    Error(
                        f"Setting '{self.name}' has incorrect type in CONSTANCE_CONFIG. Expected {self.expected_type.__name__}, got {config_value.specified_type.__name__}.",
                        hint=f"Change the type specification to {self.expected_type.__name__} in CONSTANCE_CONFIG.",
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

    # Define required constance settings with their error IDs and expected types
    required_settings = [
        # Prince PDF Generation
        RequiredSetting("PRINCE_SERVER", "touchtechnology.common.E004", str),
        RequiredSetting("PRINCE_BINARY", "touchtechnology.common.E005", str),
        RequiredSetting("PRINCE_BASE_URL", "touchtechnology.common.E006", str),
        # Touch Technology Common
        RequiredSetting("TOUCHTECHNOLOGY_APP_ROUTING", "touchtechnology.common.E007", tuple),
        RequiredSetting("TOUCHTECHNOLOGY_CURRENCY_ABBREVIATION", "touchtechnology.common.E008", str),
        RequiredSetting("TOUCHTECHNOLOGY_CURRENCY_SYMBOL", "touchtechnology.common.E009", str),
        RequiredSetting("TOUCHTECHNOLOGY_PAGINATE_BY", "touchtechnology.common.E010", int),
        RequiredSetting("TOUCHTECHNOLOGY_PROFILE_FORM_CLASS", "touchtechnology.common.E011", str),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_CACHE_DURATION", "touchtechnology.common.E012", int),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_EDIT_PARENT", "touchtechnology.common.E013", bool),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_HTTPS_OPTION", "touchtechnology.common.E014", bool),
        RequiredSetting("TOUCHTECHNOLOGY_SITEMAP_ROOT", "touchtechnology.common.E015", str),
        RequiredSetting("TOUCHTECHNOLOGY_STORAGE_FOLDER", "touchtechnology.common.E016", str),
        RequiredSetting("TOUCHTECHNOLOGY_STORAGE_URL", "touchtechnology.common.E017", str),
        # Touch Technology Content
        RequiredSetting("TOUCHTECHNOLOGY_NODE_CACHE", "touchtechnology.common.E018", str),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS", "touchtechnology.common.E019", int),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES", "touchtechnology.common.E020", tuple),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE", "touchtechnology.common.E021", str),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER", "touchtechnology.common.E022", str),
        RequiredSetting("TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX", "touchtechnology.common.E023", str),
        RequiredSetting("TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC", "touchtechnology.common.E024", bool),
        # Touch Technology News
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS", "touchtechnology.common.E025", dict),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS", "touchtechnology.common.E026", tuple),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_PAGINATE_BY", "touchtechnology.common.E027", int),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS", "touchtechnology.common.E028", dict),
        RequiredSetting("TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS", "touchtechnology.common.E029", tuple),
        # Tournament Control Competition
        RequiredSetting("TOURNAMENTCONTROL_COMPETITION_VIDEOS_ARRAY_SIZE", "touchtechnology.common.E030", int),
        RequiredSetting("TOURNAMENTCONTROL_SCORECARD_PDF_WAIT", "touchtechnology.common.E031", int),
        RequiredSetting("TOURNAMENTCONTROL_ASYNC_PDF_GRID", "touchtechnology.common.E032", bool),
        # Other
        RequiredSetting("FROALA_EDITOR_OPTIONS", "touchtechnology.common.E033", dict),
        RequiredSetting("GOOGLE_ANALYTICS", "touchtechnology.common.E034", str),
        RequiredSetting("ANONYMOUS_USER_ID", "touchtechnology.common.E035", int),
    ]

    for required_setting in required_settings:
        errors.extend(required_setting.validate())

    return errors

