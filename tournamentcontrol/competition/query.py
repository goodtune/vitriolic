from django.conf import settings
from django.db.models import Case, ExpressionWrapper, F, FloatField, Func, When
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.module_loading import import_string


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

    def _rank_importance(self):
        """
        Find the rank_importance of a match based on the competition hierarchy.
        """
        return self.annotate(
            importance=Case(
                When(rank_importance__isnull=False, then=F("rank_importance")),
                When(
                    stage_group__rank_importance__isnull=False,
                    then=F("stage_group__rank_importance"),
                ),
                When(
                    stage__rank_importance__isnull=False,
                    then=F("stage__rank_importance"),
                ),
                When(
                    stage__division__rank_importance__isnull=False,
                    then=F("stage__division__rank_importance"),
                ),
                When(
                    stage__division__season__rank_importance__isnull=False,
                    then=F("stage__division__season__rank_importance"),
                ),
                When(
                    stage__division__season__competition__rank_importance__isnull=False,
                    then=F("stage__division__season__competition__rank_importance"),
                ),
            ),
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

        qs = qs.annotate(
            division=Case(
                When(team__rank_division__isnull=False, then=F("team__rank_division")),
                When(
                    team__division__rank_division__isnull=False,
                    then=F("team__division__rank_division"),
                ),
            ),
            opponent_division=Case(
                When(
                    opponent__rank_division__isnull=False,
                    then=F("opponent__rank_division"),
                ),
                When(
                    opponent__division__rank_division__isnull=False,
                    then=F("opponent__division__rank_division"),
                ),
            ),
        )

        qs = qs.annotate(
            importance=Case(
                When(
                    match__rank_importance__isnull=False,
                    then=F("match__rank_importance"),
                ),
                When(
                    match__stage_group__rank_importance__isnull=False,
                    then=F("match__stage_group__rank_importance"),
                ),
                When(
                    match__stage__rank_importance__isnull=False,
                    then=F("match__stage__rank_importance"),
                ),
                When(
                    match__stage__division__rank_importance__isnull=False,
                    then=F("match__stage__division__rank_importance"),
                ),
                When(
                    match__stage__division__season__rank_importance__isnull=False,
                    then=F("match__stage__division__season__rank_importance"),
                ),
                When(
                    match__stage__division__season__competition__rank_importance__isnull=False,
                    then=F(
                        "match__stage__division__season__competition__rank_importance"
                    ),
                ),
                output_field=FloatField(),
            ),
        )

        RANK_POINTS_FUNC = getattr(
            settings,
            "TOURNAMENTCONTROL_RANK_POINTS_FUNC",
            "tournamentcontrol.competition.rank.points_func",
        )
        rank_points = import_string(RANK_POINTS_FUNC)
        qs = qs.annotate(
            rank_points=ExpressionWrapper(
                rank_points() * F("importance"),
                output_field=FloatField(),
            ),
        )

        return qs


class StatisticQuerySet(QuerySet):
    def played(self):
        return self.exclude(played=0)
