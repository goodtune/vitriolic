from rest_framework.routers import APIRootView, DefaultRouter
from rest_framework_nested import routers

from touchtechnology.news.rest.v1 import article


class NewsAPI(APIRootView):
    """
    REST API for *News*.
    """


class Router(DefaultRouter):
    APIRootView = NewsAPI


router = Router()
router.register(r"categories", article.CategoryViewSet)
router.register(r"articles", article.ArticleViewSet)

article_router = routers.NestedDefaultRouter(router, r"articles", lookup="article")
article_router.register(
    r"translations", article.TranslationViewSet, basename="translation"
)
