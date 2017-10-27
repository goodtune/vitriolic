from django.utils.encoding import smart_str
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from touchtechnology.common.shim import widgets


class iCheckFieldRenderer(widgets.CheckboxFieldRenderer):
    def render(self):
        """
        Outputs a <div> for this set of choice fields.
        If an id was given to the field, it is applied to the <div> (each item
        in the list will get an id of `$id_$i`).
        """
        id_ = self.attrs.get('id', None)
        if id_:
            start_tag = format_html('<div class="icheck" id="{0}">', id_)
        else:
            start_tag = '<div class="icheck">'
        output = [start_tag]
        for i, choice in enumerate(self.choices):
            choice_value, choice_label = choice
            if isinstance(choice_label, (tuple, list)):
                attrs_plus = self.attrs.copy()
                if id_:
                    attrs_plus['id'] += '_{0}'.format(i)
                sub_ul_renderer = widgets.ChoiceFieldRenderer(
                    name=self.name, value=self.value,
                    attrs=attrs_plus, choices=choice_label)
                sub_ul_renderer.choice_input_class = self.choice_input_class
                output.append(
                    format_html('<div class="checkbox">{0}{1}</div>',
                                choice_value, sub_ul_renderer.render()))
            else:
                # re-unpack the choice and handle HTML entities
                choice_value, choice_label = choice
                choice = (choice_value, mark_safe(
                    choice_label.encode('ascii', errors='xmlcharrefreplace')))
                w = self.choice_input_class(self.name, self.value,
                                            self.attrs.copy(), choice, i)
                output.append(format_html('<div class="checkbox">{0}</div>',
                                          smart_str(w)))
        output.append('</div>')
        return mark_safe('\n'.join(output))


class iCheckSelectMultiple(widgets.CheckboxSelectMultiple):
    renderer = iCheckFieldRenderer
