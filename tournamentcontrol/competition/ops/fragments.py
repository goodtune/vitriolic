from django.template.loader import render_to_string


def render_fragment(request, name, **context):
    return render_to_string(
        f"tournamentcontrol/ops/fragments/{name}.html", context, request=request
    )


def render_counts(request, **context):
    """The results and scorers counts, for the panel headers and the tab bar."""
    fragments = []
    for name in ("results_count", "scorers_count"):
        for suffix in ("", "-tab"):
            fragments.append(
                render_fragment(request, name, count_suffix=suffix, **context)
            )
    return fragments
