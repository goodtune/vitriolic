"""
``{% board %}`` ... ``{% endboard %}``: the part of a scoreboard template
written in the admin that the live updates replace.

The tag wraps what is between it in the element the updates look for, and
keeps a copy of what it rendered, so that an update can send the board alone
(see ``scoreboard.render_custom``). It is a built-in of the engine such a
template is rendered by, and of no other.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

#: The context variable that holds a list for the tag to leave the board it
#: rendered in. Django keeps nothing else of a render once it is over.
RENDERED = "compops_scoreboard_board"


class BoardNode(template.Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        board = format_html(
            # Asked for again every 20 seconds, so the board moves to the
            # next match by itself; ``data-template`` says which template
            # drew it, so the page loads again when another takes over.
            '<div id="board" data-template="{}" '
            "data-on-interval__duration.20s=\"@get('{}')\">{}</div>",
            context.get("template_key", ""),
            context.get("board_url", ""),
            mark_safe(self.nodelist.render(context)),
        )
        kept = context.get(RENDERED)
        if kept is not None:
            kept.append(board)
        return board


@register.tag
def board(parser, token):
    nodelist = parser.parse(("endboard",))
    parser.delete_first_token()
    return BoardNode(nodelist)
