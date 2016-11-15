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
    url(r'^context-processors/', include(test_context_processors.urls)),
    url(r'^date-time-field/', include(test_date_time_field.urls)),
    url(r'^generic/', include(test_generic_views.urls)),
    url(r'^query-string/', include(test_query_string.urls)),
    url(r'^pagination/', include(test_pagination.urls)),
    url(r'^accounts/', include(accounts.urls)),  # can't login without it
    url(r'^news/', include(news.urls)),
    url(r'^', include('touchtechnology.common.urls')),
    url(r'^$', views.index, name='index'),
]
