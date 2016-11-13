from django.utils.functional import cached_property


class AppRouter(object):
    """
    Allow application level routing to distinct databases. Be careful not to
    attempt foreign-key relationships across physical boundaries!

    In your DJANGO_CONFIG_MODULE you should set an iterable mapping of
    app_label to database aliases. For example:

        TOUCHTECHNOLOGY_APP_ROUTING = (
            ('foo', 'bar'),
            ('baz', 'foo'),
        )

    or

        TOUCHTECHNOLOGY_APP_ROUTING = {
            'foo': 'bar',
            'baz': 'foo',
        }

    Any app_label which is ommitted will be routed to the DEFAULT_DB_ALIAS.
    """

    @cached_property
    def route(self):
        from collections import defaultdict
        from django.db import DEFAULT_DB_ALIAS
        from .default_settings import APP_ROUTING
        return defaultdict(lambda: DEFAULT_DB_ALIAS, APP_ROUTING)

    def _route(self, model, **hints):
        return self.route[model._meta.app_label]

    db_for_read = _route
    db_for_write = _route

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return db == self.route[app_label]
