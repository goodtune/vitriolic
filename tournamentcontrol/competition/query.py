from django.db.models.query import QuerySet
from django.utils import timezone


class DivisionQuerySet(QuerySet):
    """
    QuerySet to allow divisions to be easily filtered by their draft status.
    """
    def public(self):
        return self.filter(draft=False)


class StageQuerySet(QuerySet):

    def with_ladder(self):
        return self.filter(
            keep_ladder=True, ladder_summary__isnull=False).distinct()


class MatchQuerySet(QuerySet):

    def future(self, date=None):
        if date is None:
            date = timezone.now().date()
        return self.filter(date__gte=date)

    def playable(self):
        return self.exclude(is_bye=True)

    def videos(self):
        return self.filter(videos__isnull=False).order_by('datetime').distinct()


class StatisticQuerySet(QuerySet):

    def played(self):
        return self.exclude(played=0)
