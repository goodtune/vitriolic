from django.template.loader import render_to_string
from django.utils import timezone

# The page whose template defines each partial; a fragment is that partial
# rendered on its own.
PAGES = {
    **dict.fromkeys(
        (
            "main",
            "results",
            "slot",
            "slot_header",
            "match_row",
            "results_count",
            "scorers",
            "scorers_count",
            "scorers_modal",
            "streams",
            "stream_buttons",
            "streams_count",
            "activity",
        ),
        "day",
    ),
    **dict.fromkeys(
        (
            "lamp",
            "strip",
            "pane_sheets",
            "pane_results",
            "pane_ladder",
            "pane_leaders",
            "pane_runsheet",
            "teams_modal",
            "team_modal",
        ),
        "booth",
    ),
}


def render_fragment(request, name, **context):
    """Render the partial ``name`` from the page that defines it."""

    def render():
        return render_to_string(
            f"tournamentcontrol/competition/ops/{PAGES[name]}.html#{name}",
            context,
            request=request,
        )

    ground = context.get("ground")
    if ground is not None:
        with timezone.override(ground.get_tzinfo()):
            return render()
    season = context.get("season")
    if season is not None:
        with timezone.override(season.get_tzinfo()):
            return render()
    return render()


def render_counts(request, **context):
    """The counts, for the panel headers, the tab bar and the collapsed rail."""
    fragments = []
    for name in ("results_count", "scorers_count"):
        for suffix in ("", "-tab"):
            fragments.append(
                render_fragment(request, name, count_suffix=suffix, **context)
            )
    for suffix in ("", "-rail"):
        fragments.append(
            render_fragment(request, "streams_count", count_suffix=suffix, **context)
        )
    return fragments
