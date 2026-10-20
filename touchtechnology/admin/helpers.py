"""
Helpers the admin's shells share: each shell's template tag library imports
them rather than saying them again.
"""

from django.forms import widgets as django_widgets

#: Remote assets a widget may declare, and the copy the admin serves itself.
SELF_HOSTED = {
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css": (
        "touchtechnology/admin/vendor/leaflet/leaflet.css"
    ),
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js": (
        "touchtechnology/admin/vendor/leaflet/leaflet.js"
    ),
}


def admin_media(media):
    """``media`` with the remote assets it names swapped for the admin's copies."""
    if not isinstance(media, django_widgets.Media):
        return media or ""

    def swap(asset):
        # An asset is a path or (Django 5.2 on) a Script or Stylesheet.
        path = getattr(asset, "_path", asset)
        return SELF_HOSTED.get(str(path), asset)

    js = [swap(asset) for asset in media._js]
    css = {
        medium: [swap(asset) for asset in assets]
        for medium, assets in media._css.items()
    }
    return django_widgets.Media(css=css, js=js)


def initials(user, single=1):
    """
    Up to two letters for a person with no picture, or for a name: the first
    letters of the first and last words of their full name (of their user name
    when they have no other). A name of one word gives its first ``single``
    letters.
    """
    if user is None:
        return "?"
    if hasattr(user, "get_full_name"):
        name = user.get_full_name() or user.get_username()
    else:
        name = str(user)
    words = str(name).replace(".", " ").split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:single].upper()
    return (words[0][0] + words[-1][0]).upper()
