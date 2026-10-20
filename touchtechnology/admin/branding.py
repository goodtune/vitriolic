"""[Developer API] Resolve the brand (name, logo, palette) of the admin."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

COLOUR_KEYS = ("primary", "secondary", "success", "warning", "danger")

DEFAULT_COLOURS = {
    "primary": "#275d8b",
    "secondary": "#e8862a",
    "success": "#2a8a5c",
    "warning": "#d9a21b",
    "danger": "#b8322f",
}

DEFAULT_NAME = "Administration"

COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

SETTING = "TOUCHTECHNOLOGY_ADMIN_BRAND"


@dataclass(frozen=True)
class Brand:
    """The identity the admin presents: a name, an optional logo and a palette."""

    name: str = DEFAULT_NAME
    logo: str | None = None
    colours: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COLOURS))


def brand_from(value):
    """
    Build a validated ``Brand`` from a mapping, a ``Brand`` or ``None``.

    Colours missing from the value are filled from ``DEFAULT_COLOURS``. Raises
    ``ImproperlyConfigured`` when the name, logo or any colour is invalid.
    """
    if value is None:
        return Brand()

    if isinstance(value, Brand):
        value = {"name": value.name, "logo": value.logo, "colours": value.colours}

    if not isinstance(value, Mapping):
        raise ImproperlyConfigured(
            f"{SETTING} must be a mapping, a Brand or a callable returning one, "
            f"got {value!r}"
        )

    name = value.get("name", DEFAULT_NAME)
    if not isinstance(name, str) or not name.strip():
        raise ImproperlyConfigured(
            f"{SETTING} name must be a non-empty string, got {name!r}"
        )

    logo = value.get("logo")
    if logo is not None and not isinstance(logo, str):
        raise ImproperlyConfigured(
            f"{SETTING} logo must be a string or None, got {logo!r}"
        )

    supplied = value.get("colours") or {}
    if not isinstance(supplied, Mapping):
        raise ImproperlyConfigured(
            f"{SETTING} colours must be a mapping, got {supplied!r}"
        )

    colours = dict(DEFAULT_COLOURS)
    for key in COLOUR_KEYS:
        if key not in supplied:
            continue
        colour = supplied[key]
        if not isinstance(colour, str) or not COLOUR_RE.match(colour):
            raise ImproperlyConfigured(
                f"{SETTING} colour {key!r} must be #rrggbb, got {colour!r}"
            )
        colours[key] = colour

    return Brand(name=name, logo=logo, colours=colours)


def get_brand(request=None):
    """
    Resolve the brand for ``request``.

    In order: the ``admin_brand`` attribute of the request, then the
    ``TOUCHTECHNOLOGY_ADMIN_BRAND`` setting, which may be a mapping, a ``Brand``,
    a callable taking the request or a dotted path to such a callable. When
    neither is present the default ``Brand`` is returned.
    """
    value = getattr(request, "admin_brand", None)
    if value is None:
        value = getattr(settings, SETTING, None)

    if isinstance(value, str):
        value = import_string(value)

    if callable(value) and not isinstance(value, Brand):
        value = value(request)

    return brand_from(value)


def brand_check(app_configs, **kwargs):
    """
    Report an invalid ``TOUCHTECHNOLOGY_ADMIN_BRAND`` setting at check time.

    Only a mapping or a ``Brand`` is validated. Callables, and dotted paths to
    them, are not called here as they need a request.
    """
    value = getattr(settings, SETTING, None)
    if not isinstance(value, Mapping | Brand):
        return []

    try:
        brand_from(value)
    except ImproperlyConfigured as exc:
        return [checks.Error(str(exc), id="touchtechnology_admin.E001")]

    return []
