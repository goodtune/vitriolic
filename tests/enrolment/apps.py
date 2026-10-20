from django.apps import AppConfig


class EnrolmentConfig(AppConfig):
    name = "enrolment"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Imported here as the admin module imports the models, which are not
        # ready when this module is first loaded.
        from enrolment.admin import EnrolmentAdminComponent
        from touchtechnology.admin.sites import site

        site.register(EnrolmentAdminComponent)
