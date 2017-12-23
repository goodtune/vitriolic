from django.template import Library
from django.template.loader import get_template

register = Library()


@register.simple_tag(takes_context=True)
def render(context, widget):
    tpl = get_template(widget.template)
    ctx = context.flatten()
    ctx.update(widget.context)
    return tpl.render(ctx)
