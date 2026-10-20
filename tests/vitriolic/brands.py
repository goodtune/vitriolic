"""Demo brands for the test project, selected with the ADMIN_BRAND variable."""

from touchtechnology.admin.branding import DEFAULT_COLOURS

BRANDS = {
    "default": {
        "name": "Harbour Touch Association",
        "colours": DEFAULT_COLOURS,
    },
    "forest": {
        "name": "Ridgeway Sports Trust",
        "logo": None,
        "colours": {
            "primary": "#1e3d2f",
            "secondary": "#c9a227",
            "success": "#3c8d5a",
            "warning": "#e0a62d",
            "danger": "#a63d40",
        },
    },
    "sherbet": {
        "name": "Bayside Junior League",
        "logo": None,
        "colours": {
            "primary": "#ffd166",
            "secondary": "#073b4c",
            "success": "#2a9d8f",
            "warning": "#f4a261",
            "danger": "#e63946",
        },
    },
}
