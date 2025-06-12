from django.apps import AppConfig


class HighlightsConfig(AppConfig):
    name = "tournamentcontrol.highlights"

    def ready(self):
        from touchtechnology.admin.sites import site
        from tournamentcontrol.highlights.admin import HighlightsAdminComponent

        site.register(HighlightsAdminComponent)
