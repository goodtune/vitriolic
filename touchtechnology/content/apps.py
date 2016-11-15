from django.apps import AppConfig
from django.apps import apps


class ContentConfig(AppConfig):
    name = 'touchtechnology.content'

    def ready(self):
        from touchtechnology.content.utils import install_placeholder
        for config in apps.get_app_configs():
            install_placeholder(config.name)
