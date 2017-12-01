from tournamentcontrol.competition.signals.decorators import (
    disable_for_loaddata,
)


@disable_for_loaddata
def set_ground_latlng(sender, instance, created, *args, **kwargs):
    if created and not instance.latlng:
        instance.latlng = instance.venue.latlng
        instance.save()


@disable_for_loaddata
def set_ground_timezone(sender, instance, created, *args, **kwargs):
    if created and not instance.timezone:
        instance.timezone = instance.venue.timezone
        instance.save()
