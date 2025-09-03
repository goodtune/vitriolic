from django.urls import include, path

urlpatterns = [
    path(
        "v1/",
        include(
            ("touchtechnology.news.rest.v1.urls", "api"),
            namespace="v1",
        ),
    ),
]
