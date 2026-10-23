import logging

from django.template import Library
from django.template.loader import select_template

logger = logging.getLogger(__name__)

register = Library()


@register.simple_tag(takes_context=True)
def render(context, widget):
    # A widget names its template without a shell; the shell of the page it is
    # on, if it has one, has its own.
    shell = context.get("shell")
    names = shell.names(widget.template) if shell is not None else [widget.template]
    tpl = select_template(names)
    ctx = context.flatten()
    try:
        ctx.update(widget.context)
        return tpl.render(ctx)
    except Exception:
        # One widget that cannot work out what to show must not take the
        # whole page down with it: leave it out, and say why in the log.
        logger.exception(
            "The dashboard widget %r failed and was left out of the page.",
            str(widget.verbose_name),
        )
        return ""
