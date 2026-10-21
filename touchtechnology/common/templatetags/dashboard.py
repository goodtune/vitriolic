from django.template import Library
from django.template.loader import select_template

register = Library()


@register.simple_tag(takes_context=True)
def render(context, widget):
    # A widget names its template without a shell; the shell of the page it is
    # on, if it has one, has its own.
    shell = context.get("shell")
    names = shell.names(widget.template) if shell is not None else [widget.template]
    tpl = select_template(names)
    ctx = context.flatten()
    ctx.update(widget.context)
    return tpl.render(ctx)
