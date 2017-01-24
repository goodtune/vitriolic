from .admin import AdminSite
from .auth import UsersGroups
from .settings import Settings

site = AdminSite()
site.register(Settings)
site.register(UsersGroups)
