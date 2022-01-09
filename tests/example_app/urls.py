from django.urls import include, path
from example_app import sites, views

from touchtechnology.common.sites import AccountsSite
from touchtechnology.news.sites import NewsSite

test_context_processors = sites.TestContextProcessorsSite()
test_date_time_field = sites.TestDateTimeFieldSite()
test_generic_views = sites.TestGenericViewsSite()
test_query_string = sites.TestQueryStringSite()
test_pagination = sites.TestPaginationSite()

accounts = AccountsSite()
news = NewsSite()

urlpatterns = [
    path("context-processors/", test_context_processors.urls),
    path("date-time-field/", test_date_time_field.urls),
    path("generic/", test_generic_views.urls),
    path("query-string/", test_query_string.urls),
    path("pagination/", test_pagination.urls),
    path("accounts/", accounts.urls),  # can't login without it
    path("news/", news.urls),
    path("", include("touchtechnology.common.urls")),
    path("", views.index, name="index"),
]
