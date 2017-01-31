from django.conf.urls import url
from django.views.i18n import set_language
from touchtechnology.common.views import set_timezone

urlpatterns = [
    url(r'^i18n/set-language$', set_language, name='set-language'),
    url(r'^i18n/set-timezone$', set_timezone, name='set-timezone'),
]
