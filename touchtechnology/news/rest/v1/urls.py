from touchtechnology.news.rest.v1._routers import router, article_router

urlpatterns = router.urls + article_router.urls