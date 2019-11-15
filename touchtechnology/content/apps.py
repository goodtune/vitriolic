from django.apps import AppConfig
from django.db.models.signals import post_migrate


def install_placeholder_handler(sender, **kwargs):
    from touchtechnology.content.utils import install_placeholder

    install_placeholder(sender.name)


class ContentConfig(AppConfig):
    name = "touchtechnology.content"

    def ready(self):
        from touchtechnology.admin.sites import site
        from touchtechnology.content.admin import ContentAdminComponent

        site.register(ContentAdminComponent)
        post_migrate.connect(install_placeholder_handler)
