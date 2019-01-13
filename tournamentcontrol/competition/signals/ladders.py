import logging
from decimal import Decimal, DivisionByZero, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Sum
from tournamentcontrol.competition.signals.decorators import disable_for_loaddata
from tournamentcontrol.competition.utils import SumDict

logger = logging.getLogger(__name__)

aggregate_kw = dict(
    played=Sum('played'),
    win=Sum('win'),
    loss=Sum('loss'),
    draw=Sum('draw'),
    bye=Sum('bye'),
    forfeit_for=Sum('forfeit_for'),
    forfeit_against=Sum('forfeit_against'),
    score_for=Sum('score_for'),
    score_against=Sum('score_against'),
    bonus_points=Sum('bonus_points'),
    points=Sum('points'),
)


@disable_for_loaddata
def changed_points_formula(sender, instance, *args, **kwargs):
    """
    When the ``points_formula`` is edited, we need to trigger a rebuild of all
    matches that have results and are related to the updated instance.
    """
    if 'points_formula' in instance.changed_fields:
        for m in instance.matches.filter(ladder_entries__isnull=False):
            m.save()


@disable_for_loaddata
def scale_ladder_entry(sender, instance, *args, **kwargs):
    """
    When there are pools of different sizes, it may be desirable to scale the
    number of points earned in the smaller group/s to allow comparison with
    larger groups.

    If enabled, this evaulation will be performed by applying the formula

        value / t * T

    where ``t`` is the number of teams in the small group, and ``T`` is the
    number of teams in the largest group.
    """
    if not instance.stage.scale_group_points:
        logger.debug('%r has not enabled point scaling, skip.',
                     instance.stage)
        return

    if instance.stage_group is None:
        logger.debug('%r is not part of a stage with pools, skip.',
                     instance)
        return

    # Precalculation to assist in group size calculations. Exclude matches
    # that are marked as a Bye as these are "unplayable" and are effectively
    # the difference between divisions.
    stages = instance.stage.pools.exclude(matches__is_bye=True)
    stages = stages.annotate(count=Count('matches'))

    # Determine the size of the group in question, and the largest group in
    # this Stage.
    t = instance.stage_group.teams.count()
    T = max(instance.stage.pools.annotate(
            count=Count('teams')).values_list('count', flat=True))

    if t == T:
        logger.debug('%r is one of the large pools, skip.',
                     instance.stage_group)
        return

    # Convert ``t`` and ``T`` to Decimal type
    t = Decimal(t)
    T = Decimal(T)

    # Determine the adjusted value for the points
    points = instance.points / t * T
    logger.debug('%s / %s * %s = %s', instance.points, t, T, points)

    # Update the points value after adjustment
    instance.difference = instance.difference / t * T
    instance.percentage = instance.percentage / t * T
    instance.points = instance.points / t * T


@disable_for_loaddata
def team_ladder_entry_aggregation(sender, instance, created=None,
                                  *args, **kwargs):
    """
    Function to be called following a LadderEntry being saved.

    The should recalculate the LadderSummary for a particular team in a
    particular division so that we don't have to do too many database hits and
    calculations for ladders.

    We can also sort a ladder for a division easily this way without need to
    calculate and then compare.
    """
    try:
        instance.team.ladder_summary.filter(
            stage=instance.match.stage).delete()
    except ObjectDoesNotExist as e:
        logger.debug(e)

    if not instance.match.stage.keep_ladder:
        logger.debug('Stage does not keep a ladder, skipping.')
        return

    # if we are carrying points from the previous stage then we'll need to add
    # them here.

    base = SumDict()
    if instance.match and instance.match.stage_group:
        home_pks = instance.match.stage_group.matches.values_list(
            'home_team', flat=True)
        away_pks = instance.match.stage_group.matches.values_list(
            'away_team', flat=True)
        opponent_pks = set(home_pks).union(away_pks).difference(
            [instance.team_id])

        # when the Pool has carry_ladder set we want to only bring forward the
        # statistics from matches played with other teams in the group.
        if instance.match.stage_group.carry_ladder:
            logger.debug('Pool match, group statistics only.')
            base += instance.team.ladder_entries.filter(
                match__include_in_ladder=True,
                match__stage=instance.match.stage.comes_after,
                opponent__in=opponent_pks).aggregate(**aggregate_kw)

        # when the Stage has carry_ladder set but not the Pool we want to
        # bring forward all the teams statistics from the preceding stage.
        elif instance.match.stage.carry_ladder:
            logger.debug('Pool match, all stage statistics.')
            base += instance.team.ladder_entries.filter(
                match__include_in_ladder=True,
                match__stage=instance.match.stage.comes_after).aggregate(
                **aggregate_kw)

    elif instance.match.stage.carry_ladder:
        # when the preceeding stage had Pools, this stage does not have any
        # Pools, and carry_ladder is set, then we would bring forward the
        # statistics from matches played with other teams in the stage.
        if instance.match.stage.comes_after.pools.count():
            base += instance.team.ladder_entries.filter(
                match__include_in_ladder=True,
                match__stage=instance.match.stage.comes_after,
                opponent__in=instance.match.stage.teams).aggregate(
                **aggregate_kw)

        # when there are no Pools and the stage has carry_ladder set we bring
        # forward the ladder_summary instead.
        else:
            base += instance.team.ladder_summary.filter(
                stage=instance.match.stage.comes_after).aggregate(
                **aggregate_kw)

    aggregate = base + instance.team.ladder_entries.filter(
        match__include_in_ladder=True,
        match__stage=instance.match.stage,
        ).aggregate(**aggregate_kw)

    score_for = aggregate.get('score_for')
    score_against = aggregate.get('score_against')

    try:
        difference = score_for - score_against
    except TypeError:
        difference = None

    try:
        percentage = Decimal(score_for) / Decimal(score_against) * Decimal(100)
    except (DivisionByZero, InvalidOperation, TypeError):
        percentage = None

    aggregate.update({'difference': difference})
    aggregate.update({'percentage': percentage})

    instance.team.ladder_summary.create(
        stage=instance.match.stage,
        stage_group=instance.match.stage_group,
        **aggregate)
