import logging

from modelforms.forms import ModelForm

logger = logging.getLogger(__name__)


class RedefineModelForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(RedefineModelForm, self).__init__(*args, **kwargs)
        for field, _kw in self.Meta.redefine:
            kw = {}
            for key, val in _kw.items():
                if callable(val) and not type(val) == type:
                    kw[key] = val(self.fields[field])
                else:
                    kw[key] = val
            model_field = self.Meta.model._meta.get_field(field)
            self.fields[field] = model_field.formfield(**kw)
