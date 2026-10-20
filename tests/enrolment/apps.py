from django.apps import AppConfig


class EnrolmentConfig(AppConfig):
    name = "enrolment"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        pass
