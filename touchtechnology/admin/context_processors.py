from touchtechnology.admin.branding import get_brand


def brand(request):
    return {"brand": get_brand(request)}
