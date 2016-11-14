from .admin import AdminSite
from .settings import Settings
from .auth import UsersGroups

site = AdminSite()
site.register(Settings)
site.register(UsersGroups)
