"""[Developer API] App configuration for the news module."""

from django.apps import AppConfig


class NewsConfig(AppConfig):
    """Registers the News app with the admin interface."""

    name = "touchtechnology.news"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        """Attach News admin components to the global site."""
        from touchtechnology.admin.sites import site
        from touchtechnology.news.admin import NewsAdminComponent

        site.register(NewsAdminComponent)
