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


@disable_for_loaddata
def capture_timezone_before_save(sender, instance, **kwargs):
    """Capture the current timezone before saving to detect changes."""
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_timezone = old_instance.timezone
        except sender.DoesNotExist:
            instance._old_timezone = None
    else:
        instance._old_timezone = None


@disable_for_loaddata
def update_match_datetimes_on_place_timezone_change(
    sender, instance, created, **kwargs
):
    """Update Match.datetime when Place (Venue/Ground) timezone changes."""
    if not created and hasattr(instance, "_old_timezone"):
        old_timezone = instance._old_timezone
        new_timezone = instance.timezone

        if old_timezone != new_timezone:
            # Update all matches played at this place (venue or ground)
            matches = instance.match_set.filter(date__isnull=False, time__isnull=False)
            for match in matches:
                match.clean()  # Recalculate datetime with new timezone
                match.save(update_fields=["datetime"])
