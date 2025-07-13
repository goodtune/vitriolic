from rest_framework import viewsets


class SlugViewSet(viewsets.ModelViewSet):
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "list" and hasattr(self, "list_serializer_class"):
            return self.list_serializer_class
        return super().get_serializer_class()
