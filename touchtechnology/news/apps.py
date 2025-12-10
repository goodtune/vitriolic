"""[Developer API] App configuration for the news module."""

from django.apps import AppConfig


class NewsConfig(AppConfig):
    """Registers the News app with the admin interface."""

    name = "touchtechnology.news"

    def ready(self):
        """Attach News admin components to the global site and initialize image fields."""
        # Initialize ImageSpecFields after app is ready to avoid accessing
        # constance config during model definition
        try:
            from constance import config
            from imagekit.models import ImageSpecField

            from touchtechnology.news.image_processors import processor_factory
            from touchtechnology.news.models import Article

            if Article.thumbnail is None:
                Article.thumbnail = ImageSpecField(
                    source="image",
                    processors=processor_factory(
                        config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS
                    ),
                    **config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS,
                )
                Article.thumbnail.contribute_to_class(Article, "thumbnail")

            if Article.detail_image is None:
                Article.detail_image = ImageSpecField(
                    source="image",
                    processors=processor_factory(
                        config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS
                    ),
                    **config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS,
                )
                Article.detail_image.contribute_to_class(Article, "detail_image")
        except Exception:
            # If constance is not ready (e.g., during migrations), skip image field setup
            # They will use defaults or be set up later
            pass

        from touchtechnology.admin.sites import site
        from touchtechnology.news.admin import NewsAdminComponent

        site.register(NewsAdminComponent)
