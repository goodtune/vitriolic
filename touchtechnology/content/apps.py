"""[Developer API] App configuration for the content module."""

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def install_placeholder_handler(sender, **kwargs):
    from touchtechnology.content.utils import install_placeholder

    """Install placeholder pages after migrations run."""

    install_placeholder(sender.name)


class ContentConfig(AppConfig):
    """Integrates content admin components and post-migrate hooks."""

    name = "touchtechnology.content"

    def ready(self):
        """Register admin component and placeholder handler."""
        from touchtechnology.admin.sites import site
        from touchtechnology.content.admin import ContentAdminComponent

        site.register(ContentAdminComponent)
        post_migrate.connect(install_placeholder_handler)
