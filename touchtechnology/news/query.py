from django.db.models.query import QuerySet
from django.utils import timezone


class ArticleQuerySet(QuerySet):

    def active(self):
        return self.filter(is_active=True)

    def live(self):
        return self.filter(published__lte=timezone.now()).active()


class CategoryQuerySet(QuerySet):

    def live(self):
        return self.filter(is_active=True)
