from django.conf import settings
from django.db.models import Case, ExpressionWrapper, F, FloatField, Func, When
from django.db.models.query import QuerySet
from django.utils import timezone

from tournamentcontrol.competition.utils import team_title_case_clause


class DivisionQuerySet(QuerySet):
    """
    QuerySet to allow divisions to be easily filtered by their draft status.
    """

    def public(self):
        return self.filter(draft=False)


class StageQuerySet(QuerySet):
    def with_ladder(self):
        return self.filter(keep_ladder=True, ladder_summary__isnull=False).distinct()


class MatchQuerySet(QuerySet):
    def future(self, date=None):
        if date is None:
            date = timezone.now().date()
        return self.filter(date__gte=date)

    def playable(self):
        return self.exclude(is_bye=True)

    def videos(self):
        return self.filter(videos__isnull=False).order_by("datetime").distinct()

    def _team_titles(self):
        """
        Calculate a placeholder title for teams that will require progression.
        """
        return self.annotate(
            home_team_title=team_title_case_clause("home_team"),
            away_team_title=team_title_case_clause("away_team"),
        )


class LadderEntryQuerySet(QuerySet):
    def _all(self):
        qs = self.annotate(
            diff=F("score_for") - F("score_against"),
            margin=Func(
                F("score_for") - F("score_against"),
                function="ABS",
                output_field=FloatField(),
            ),
        )

        qs = qs.select_related("team__club")

        return qs


class StatisticQuerySet(QuerySet):
    def played(self):
        return self.exclude(played=0)
