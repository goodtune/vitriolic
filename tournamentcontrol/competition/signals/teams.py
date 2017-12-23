from django.db.models import F
from tournamentcontrol.competition.signals.decorators import (
    disable_for_loaddata,
)


@disable_for_loaddata
def delete_team(sender, instance, *args, **kwargs):
    """
    When a ``Team`` is deleted we want to fix the ordering of the neighbours
    to not leave any gaps in sequences.
    """
    instance.division.teams.filter(order__gt=instance.order) \
                           .update(order=F('order') - 1)
