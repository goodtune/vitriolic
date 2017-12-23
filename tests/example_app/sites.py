from django.conf.urls import include, url
from example_app.models import Relative, TestDateTimeField
from touchtechnology.common.sites import Application


class TestDateTimeFieldSite(Application):

    def __init__(self, name='datetime', app_name='datetime', *args, **kwargs):
        super(TestDateTimeFieldSite, self).__init__(
            name=name, app_name=app_name, *args, **kwargs)

    def get_urls(self):
        urlpatterns = [
            url('^$', self.index, name='index'),
        ]
        return urlpatterns

    def index(self, request, *args, **kwargs):
        return self.generic_edit_related(
            request, TestDateTimeField, Relative)


class TestQueryStringSite(Application):

    def __init__(self, name='querystring', app_name='querystring', *args,
                 **kwargs):
        super(TestQueryStringSite, self).__init__(
            name=name, app_name=app_name, *args, **kwargs)

    def get_urls(self):
        urlpatterns = [
            url(r'^$', self.index, name='index'),
        ]
        return urlpatterns

    def index(self, request, *args, **kwargs):
        queryset = TestDateTimeField.objects.order_by('pk')

        # naive filtering without a form - nasty, i know...
        year = request.GET.get('year')
        if year:
            queryset = queryset.filter(datetime__year=year)
            month = request.GET.get('month')
            if month:
                queryset = queryset.filter(datetime__month=month)

        return self.generic_list(request, TestDateTimeField,
                                 queryset=queryset)


class TestContextProcessorsSite(Application):

    def __init__(self, name='context', app_name='context', *args, **kwargs):
        super(TestContextProcessorsSite, self).__init__(
            name=name, app_name=app_name, *args, **kwargs)

    def get_urls(self):
        urlpatterns = [
            url(r'^env$', self.env, name='env'),
            url(r'^site$', self.site_view, name='site'),
            url(r'^tz$', self.tz, name='tz'),
        ]
        return urlpatterns

    def env(self, request, *args, **kwargs):
        return self.render(request, self.template_path('env.html'), {})

    def site_view(self, request, *args, **kwargs):
        return self.render(request, self.template_path('site.html'), {})

    def tz(self, request, *args, **kwargs):
        return self.render(request, self.template_path('tz.html'), {})


class TestPaginationSite(Application):

    def __init__(self, name='pagination', app_name='pagination',
                 *args, **kwargs):
        super(TestPaginationSite, self).__init__(
            name=name, app_name=app_name, *args, **kwargs)

    def get_urls(self):
        urlpatterns = [
            url(r'^setting-only/$',
                self.setting_only, name='setting_only'),
            url(r'^parameter/(?P<paginate_by>\d+)/$',
                self.parameter, name='parameter'),
        ]
        return urlpatterns

    def setting_only(self, request, *args, **kwargs):
        return self.generic_list(request, TestDateTimeField)

    def parameter(self, request, paginate_by, *args, **kwargs):
        return self.generic_list(request, TestDateTimeField,
                                 paginate_by=paginate_by)


class TestGenericViewsSite(Application):

    def __init__(self, name='generic', app_name='generic', *args, **kwargs):
        super(TestGenericViewsSite, self).__init__(
            name=name, app_name=app_name, *args, **kwargs)

    def get_urls(self):
        urlpatterns = [
            url(r'^vanilla/', include(([
                url(r'^$', self.list, name='list'),
                url(r'^add/$', self.edit, name='add'),
                url(r'^(?P<pk>\d+)/$', self.detail, name='detail'),
                url(r'^(?P<pk>\d+)/edit/$', self.edit, name='edit'),
                url(r'^(?P<pk>\d+)/delete/$', self.delete, name='delete'),
                url(r'^(?P<pk>\d+)/perms/$', self.perms, name='perms'),
                url(r'^edit/$', self.edit_multiple, name='edit'),
            ], self.app_name), namespace='vanilla')),
            url(r'^permissions/', include(([
                url(r'^$', self.list_with_perms, name='list'),
                url(r'^add/$', self.edit_with_perms, name='add'),
                url(r'^(?P<pk>\d+)/$', self.detail_with_perms, name='detail'),
                url(r'^(?P<pk>\d+)/edit/$', self.edit_with_perms, name='edit'),
                url(r'^(?P<pk>\d+)/delete/$',
                    self.delete_with_perms, name='delete'),
                url(r'^edit/$', self.edit_multiple_with_perms, name='edit'),
            ], self.app_name), namespace='permissions')),
        ]
        return urlpatterns

    def list(self, request, **extra_context):
        return self.generic_list(request, TestDateTimeField,
                                 extra_context=extra_context)

    def detail(self, request, pk, **extra_context):
        return self.generic_detail(request, TestDateTimeField, pk=pk,
                                   extra_context=extra_context)

    def edit(self, request, pk=None, **extra_context):
        return self.generic_edit(request, TestDateTimeField, pk=pk,
                                 extra_context=extra_context)

    def delete(self, request, pk, **kwargs):
        return self.generic_delete(request, TestDateTimeField, pk=pk, **kwargs)

    def perms(self, request, pk, **extra_context):
        return self.generic_permissions(request, TestDateTimeField, pk=pk,
                                        extra_context=extra_context)

    def edit_multiple(self, request, **extra_context):
        return self.generic_edit_multiple(request, TestDateTimeField,
                                          extra_context=extra_context)

    def list_with_perms(self, request, **extra_context):
        return self.generic_list(request, TestDateTimeField,
                                 permission_required=True,
                                 extra_context=extra_context)

    def edit_with_perms(self, request, pk=None, **extra_context):
        return self.generic_edit(request, TestDateTimeField, pk=pk,
                                 permission_required=True,
                                 extra_context=extra_context)

    def delete_with_perms(self, request, pk, **kwargs):
        return self.generic_delete(request, TestDateTimeField, pk=pk,
                                   permission_required=True, **kwargs)

    def edit_multiple_with_perms(self, request, **extra_context):
        return self.generic_edit_multiple(request, TestDateTimeField,
                                          permission_required=True,
                                          extra_context=extra_context)

    def detail_with_perms(self, request, pk, **extra_context):
        return self.generic_detail(request, TestDateTimeField, pk=pk,
                                   # permission_required=True,
                                   extra_context=extra_context)
