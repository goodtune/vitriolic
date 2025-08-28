# -*- coding: utf-8 -*-

from django.db.models import Case, ExpressionWrapper, F, FloatField, Q, When

# Filter to determine which LadderEntry records get a rank_points attribute.
# Used by points_func which is dynamically imported in query.py:152
RANK_POINTS_Q = Q(match__is_bye=False, match__is_forfeit=False) | (
    (Q(match__is_forfeit=True) & ~Q(match__forfeit_winner=F("team")))
    & Q(division=F("opponent_division"))
)


# This function is still used via dynamic import in query.py:152
# TOURNAMENTCONTROL_RANK_POINTS_FUNC setting defaults to this function
def points_func(win=15.0, draw=10.0, loss=5.0, forfeit_against=-20.0):
    "This version preserves the bug from the original implementation."
    expr = (
        F("win") * win
        + F("draw") * draw
        + F("loss") * loss
        + F("forfeit_against") * forfeit_against
        +
        # The original implementation did not choose one of these, it applied
        # all that were true. For the winning bonuses this meant a massive
        # accumulator for blowout scores (1.5 times greater than was intended).
        Case(
            When(Q(win=1, margin__gt=15), then=win * 3.5),
            When(Q(win=1, margin__gt=10), then=win * 1.5),
            When(Q(win=1, margin__gt=5), then=win * 0.5),
            When(Q(loss=1, margin__lt=2), then=loss * 0.5),
            default=0,
            output_field=FloatField(),
        )
    )
    return ExpressionWrapper(
        Case(When(RANK_POINTS_Q, then=expr), default=None), output_field=FloatField()
    )
