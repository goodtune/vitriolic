from django.template.loader import render_to_string


def render_fragment(request, name, **context):
    return render_to_string(
        f"tournamentcontrol/ops/fragments/{name}.html", context, request=request
    )
