from rest_framework import viewsets


class SlugViewSet(viewsets.ModelViewSet):
    lookup_field = "slug"

    def get_queryset(self):
        if self.action == "list":
            print("-----------@!@@#$@$@$-----------")
        return super(SlugViewSet, self).get_queryset()

    def get_serializer_class(self):
        if self.action == "list" and hasattr(self, "list_serializer_class"):
            return self.list_serializer_class
        return super(SlugViewSet, self).get_serializer_class()
