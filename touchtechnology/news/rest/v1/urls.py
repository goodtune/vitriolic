from touchtechnology.news.rest.v1._routers import article_router, router

urlpatterns = router.urls + article_router.urls
