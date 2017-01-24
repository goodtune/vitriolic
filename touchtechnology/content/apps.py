from django.apps import AppConfig, apps


class ContentConfig(AppConfig):
    name = 'touchtechnology.content'

    def ready(self):
        from touchtechnology.content.utils import install_placeholder
        for config in apps.get_app_configs():
            install_placeholder(config.name)
