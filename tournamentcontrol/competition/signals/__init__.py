from django.db import models
from tournamentcontrol.competition.signals.custom import match_forfeit  # noqa
from tournamentcontrol.competition.signals.ladders import (  # noqa
    changed_points_formula, scale_ladder_entry, team_ladder_entry_aggregation,
)
from tournamentcontrol.competition.signals.matches import (  # noqa
    match_saved_handler, notify_match_forfeit_email,
)
from tournamentcontrol.competition.signals.places import (  # noqa
    set_ground_latlng, set_ground_timezone,
)
from tournamentcontrol.competition.signals.teams import delete_team  # noqa


def delete_related(sender, instance, *args, **kwargs):
    for ro, __ in [
            (f, f.model)
            for f in instance._meta.get_fields()
            if (f.one_to_many or f.one_to_one) and
            f.auto_created and not f.concrete]:
        name = ro.get_accessor_name()
        if isinstance(ro.field, models.ManyToManyField):
            continue
        if isinstance(instance, ro.model):
            continue
        manager = getattr(instance, name)
        for obj in manager.all():
            obj.delete()
