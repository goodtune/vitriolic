from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "touchtechnology.common"
    verbose_name = "Touch Technology Common"

    def ready(self):
        from . import checks  # noqa
