"""[Developer API] Base configuration for common utilities."""

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Loads system checks for shared functionality."""

    name = "touchtechnology.common"
    verbose_name = "Touch Technology Common"

    def ready(self):
        """Import Django system checks on startup."""
        from . import checks  # noqa
