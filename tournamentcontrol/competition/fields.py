import collections

from types import SimpleNamespace

from django import forms
from django.db import models

from tournamentcontrol.competition.calc import Calculator

valid_ladder_identifiers = collections.OrderedDict(
    (
        ("win", "Win"),
        ("draw", "Draw"),
        ("loss", "Loss"),
        ("bye", "Bye"),
        ("forfeit_for", "Win by forfeit"),
        ("forfeit_against", "Loss by forfeit"),
        # Other potential identifiers, but they don't really make sense as
        # variables for use in generating a ladder formula.
        #
        # 'score_for', 'score_against', 'played'
    )
)


def ladder_points_widget(name, **attrs):
    defaults = {"placeholder": valid_ladder_identifiers[name].lower()}
    defaults.update(attrs)
    return forms.TextInput(attrs=defaults)


class LadderPointsWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        self.attrs = attrs or {}

        widgets = tuple(
            [ladder_points_widget(n, **self.attrs) for n in valid_ladder_identifiers]
        )
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return ""
        values = []
        for i in valid_ladder_identifiers:
            ladder_entry = SimpleNamespace(**{i: 1})
            calc = Calculator(ladder_entry)
            calc.parse(value)
            values.append(calc.evaluate() or None)
        return values

    def format_output(self, rendered_widgets):
        output = ""
        for label, widget in zip(valid_ladder_identifiers.values(), rendered_widgets):
            output += f"""
                <div class="field_wrapper">
                    <label class="field_name">{label}</label>
                    <div class="field text_input short">
                        {widget}
                    </div>
                </div>
            """
        return output


class LadderPointsFormField(forms.MultiValueField):
    def __init__(self, max_length=None, *args, **kwargs):
        fields = tuple(
            map(
                lambda field: forms.IntegerField(required=False, initial=0),
                valid_ladder_identifiers,
            )
        )
        kwargs["widget"] = LadderPointsWidget()
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        parts = [
            "{}*{}".format(*each)
            for each in zip(data_list, valid_ladder_identifiers)
            if each[0]
        ]
        return " + ".join(parts)


class LadderPointsField(models.TextField):
    def formfield(self, form_class=None, **kwargs):
        if form_class is None:
            form_class = LadderPointsFormField
        return super().formfield(form_class=form_class, **kwargs)


class URLInput(forms.URLInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {"class": "form-control"}
        super().__init__(attrs)


class URLField(forms.URLField):
    widget = URLInput
