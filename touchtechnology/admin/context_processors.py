from touchtechnology.admin.branding import get_brand
from touchtechnology.admin.sites import site


def brand(request):
    return {"brand": get_brand(request), "shell": site.shell}
