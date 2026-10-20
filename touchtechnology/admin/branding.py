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

# The static path the admin shell always showed before it was branded, so a
# deployment with no brand setting sees the navbar it had.
DEFAULT_LOGO = "img/logo.png"

COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

SETTING = "TOUCHTECHNOLOGY_ADMIN_BRAND"


@dataclass(frozen=True)
class Brand:
    """
    The identity the admin presents: a name, a logo and a palette.

    A ``logo`` of ``None`` shows the name as a text mark instead.
    """

    name: str = DEFAULT_NAME
    logo: str | None = DEFAULT_LOGO
    colours: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COLOURS))


def brand_from(value):
    """
    Build a validated ``Brand`` from a mapping, a ``Brand`` or ``None``.

    Colours missing from the value are filled from ``DEFAULT_COLOURS``, and a
    missing ``logo`` key means ``DEFAULT_LOGO`` (an explicit ``None`` means the
    text mark). Raises ``ImproperlyConfigured`` when the name, logo or any
    colour is invalid, or a colour key is not one of ``COLOUR_KEYS``.
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

    logo = value.get("logo", DEFAULT_LOGO)
    if logo is not None and not isinstance(logo, str):
        raise ImproperlyConfigured(
            f"{SETTING} logo must be a string or None, got {logo!r}"
        )

    supplied = value.get("colours") or {}
    if not isinstance(supplied, Mapping):
        raise ImproperlyConfigured(
            f"{SETTING} colours must be a mapping, got {supplied!r}"
        )

    unknown = [key for key in supplied if key not in COLOUR_KEYS]
    if unknown:
        raise ImproperlyConfigured(
            f"{SETTING} colour {unknown[0]!r} is not one of {', '.join(COLOUR_KEYS)}"
        )

    colours = dict(DEFAULT_COLOURS)
    for key in COLOUR_KEYS:
        if key not in supplied:
            continue
        colour = supplied[key]
        if not isinstance(colour, str) or not COLOUR_RE.fullmatch(colour):
            raise ImproperlyConfigured(
                f"{SETTING} colour {key!r} must be #rrggbb, got {colour!r}"
            )
        colours[key] = colour

    return Brand(name=name, logo=logo, colours=colours)


def _setting_value():
    """
    The ``TOUCHTECHNOLOGY_ADMIN_BRAND`` setting, with a dotted path imported.
    """
    value = getattr(settings, SETTING, None)
    if isinstance(value, str):
        path = value
        try:
            value = import_string(path)
        except ImportError as exc:
            raise ImproperlyConfigured(
                f"{SETTING} cannot import {path!r}: {exc}"
            ) from exc
        if not callable(value):
            raise ImproperlyConfigured(
                f"{SETTING} path {path!r} must name a callable, "
                f"got {type(value).__name__}"
            )
    return value


def get_brand(request=None):
    """
    Resolve the brand for ``request``.

    In order: the ``admin_brand`` attribute of the request, then the
    ``TOUCHTECHNOLOGY_ADMIN_BRAND`` setting, which may be a mapping, a ``Brand``,
    a callable taking the request or a dotted path to such a callable. Only the
    setting may be a dotted path. When neither is present the default ``Brand``
    is returned.

    The result is kept on the request as ``_admin_brand`` so a callable is
    evaluated once per request however many places ask for the brand.
    """
    cached = getattr(request, "_admin_brand", None)
    if cached is not None:
        return cached

    value = getattr(request, "admin_brand", None)
    if value is None:
        value = _setting_value()
    elif isinstance(value, str):
        raise ImproperlyConfigured(
            f"request.admin_brand must be a mapping, a Brand or a callable "
            f"returning one, not the string {value!r}"
        )

    if callable(value) and not isinstance(value, Brand):
        value = value(request)

    brand = brand_from(value)
    if request is not None:
        request._admin_brand = brand
    return brand


def brand_check(app_configs, **kwargs):
    """
    Report an invalid ``TOUCHTECHNOLOGY_ADMIN_BRAND`` setting at check time.

    A mapping or a ``Brand`` is validated in full. A callable, or a dotted path
    to one, is not called here as it needs a request, but the path must import
    and name a callable. Anything else is refused.
    """
    try:
        value = _setting_value()
    except ImproperlyConfigured as exc:
        return [checks.Error(str(exc), id="touchtechnology_admin.E001")]

    if value is None:
        return []

    if isinstance(value, Mapping | Brand):
        try:
            brand_from(value)
        except ImproperlyConfigured as exc:
            return [checks.Error(str(exc), id="touchtechnology_admin.E001")]
        return []

    if callable(value):
        return []

    return [
        checks.Error(
            f"{SETTING} must be None, a mapping, a Brand, a callable or a dotted "
            f"path to one, got {type(value).__name__}",
            id="touchtechnology_admin.E001",
        )
    ]
