from django.apps import AppConfig
from django.db.models.signals import post_migrate


def install_placeholder_handler(sender, apps, **kwargs):
    from touchtechnology.content.utils import install_placeholder
    # for config in apps.get_app_configs():
    #     install_placeholder(config.name)


class ContentConfig(AppConfig):
    name = "touchtechnology.content"

    def ready(self):
        post_migrate.connect(install_placeholder_handler, sender=self)
