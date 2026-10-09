from django.template.loader import render_to_string
from django.utils import timezone


def render_fragment(request, name, **context):
    def render():
        return render_to_string(
            f"tournamentcontrol/ops/fragments/{name}.html", context, request=request
        )

    season = context.get("season")
    if season is not None and season.timezone:
        with timezone.override(season.timezone):
            return render()
    return render()


def render_counts(request, **context):
    """The results and scorers counts, for the panel headers and the tab bar."""
    fragments = []
    for name in ("results_count", "scorers_count"):
        for suffix in ("", "-tab"):
            fragments.append(
                render_fragment(request, name, count_suffix=suffix, **context)
            )
    return fragments
