from django.apps import AppConfig


class NewsConfig(AppConfig):
    name = "touchtechnology.news"

    def ready(self):
        from touchtechnology.admin.sites import site
        from touchtechnology.news.admin import NewsAdminComponent

        site.register(NewsAdminComponent)
