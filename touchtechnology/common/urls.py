from django.urls import path
from django.views.i18n import set_language

from touchtechnology.common.views import set_timezone

urlpatterns = [
    path("i18n/set-language/", set_language, name="set-language"),
    path("i18n/set-timezone/", set_timezone, name="set-timezone"),
]
