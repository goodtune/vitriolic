from django.conf.urls import include, url
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
    url(r'^context-processors/', test_context_processors.urls),
    url(r'^date-time-field/', test_date_time_field.urls),
    url(r'^generic/', test_generic_views.urls),
    url(r'^query-string/', test_query_string.urls),
    url(r'^pagination/', test_pagination.urls),
    url(r'^accounts/', accounts.urls),  # can't login without it
    url(r'^news/', news.urls),
    url(r'^', include('touchtechnology.common.urls')),
    url(r'^$', views.index, name='index'),
]
