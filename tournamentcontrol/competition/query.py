from django.apps import apps
from django.conf import settings
from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Func,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    When,
)
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

    def with_ladder_data(self):
        """
        Annotate ``pool_count`` and prefetch everything required to
        render the ladder structure used by ``Division.ladders`` — each
        stage's ``ladder_summary`` and each of its pools' ``ladder_summary``
        — with ``team__club`` joined in a single SQL statement per
        relation.

        Keeps the N+1-safe prefetch construction co-located with the
        ``StageQuerySet`` so any view that needs the same shape can reuse
        it without duplicating ``Prefetch`` boilerplate.
        """
        LadderSummary = apps.get_model("competition", "LadderSummary")
        StageGroup = apps.get_model("competition", "StageGroup")
        ladder_summary_qs = LadderSummary.objects.select_related("team__club")
        return (
            self.annotate(pool_count=Count("pools"))
            .prefetch_related(
                Prefetch("ladder_summary", queryset=ladder_summary_qs),
                Prefetch(
                    "pools",
                    queryset=StageGroup.objects.prefetch_related(
                        Prefetch("ladder_summary", queryset=ladder_summary_qs),
                    ),
                ),
            )
        )


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


class TeamAssociationQuerySet(QuerySet):
    def with_statistics(self, team):
        """
        Total each person's played, points and MVP counts for ``team``.

        ``TeamAssociation.statistics()`` makes a query of its own for every
        person, so a team page with a roster of twenty made twenty more. This
        does the same sums, over the same matches, as one subquery for each
        in the query which fetches the roster; ``statistics()`` returns them
        without asking the database again.
        """
        SimpleScoreMatchStatistic = apps.get_model(
            "competition", "SimpleScoreMatchStatistic"
        )
        stats = SimpleScoreMatchStatistic.objects.filter(
            Q(match__home_team=team) | Q(match__away_team=team),
            player=OuterRef("person"),
        ).order_by()

        def total(field):
            return Subquery(
                stats.values("player").annotate(total=Sum(field)).values("total")
            )

        return self.annotate(
            stat_played=total("played"),
            stat_points=total("points"),
            stat_mvp=total("mvp"),
        )
