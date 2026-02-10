from django.db.models import Min
from django.utils.encoding import smart_str
from mptt.forms import TreeNodeChoiceField


class MinTreeNodeChoiceField(TreeNodeChoiceField):
    @property
    def minimum_level(self):
        if not hasattr(self, "_minimum_level"):
            self._minimum_level = self.queryset.aggregate(minimum=Min("level")).get(
                "minimum"
            )
        return self._minimum_level

    def label_from_instance(self, obj):
        return f"{self.level_indicator * (obj.level - self.minimum_level)} {smart_str(obj)}"
