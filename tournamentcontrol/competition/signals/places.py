from django.db.models.signals import post_save

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
def update_match_datetimes_on_venue_timezone_change(sender, instance, created, **kwargs):
    """Update Match.datetime when Venue timezone changes."""
    if not created:
        # Check if timezone field changed
        from tournamentcontrol.competition.models import Match
        
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.timezone != instance.timezone:
                # Update all matches played at this venue
                matches = Match.objects.filter(play_at=instance, date__isnull=False, time__isnull=False)
                for match in matches:
                    match.clean()  # Recalculate datetime with new timezone
                    match.save(update_fields=['datetime'])
        except sender.DoesNotExist:
            pass


@disable_for_loaddata
def update_match_datetimes_on_ground_timezone_change(sender, instance, created, **kwargs):
    """Update Match.datetime when Ground timezone changes."""
    if not created:
        # Check if timezone field changed
        from tournamentcontrol.competition.models import Match
        
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.timezone != instance.timezone:
                # Update all matches played at this ground
                matches = Match.objects.filter(play_at=instance, date__isnull=False, time__isnull=False)
                for match in matches:
                    match.clean()  # Recalculate datetime with new timezone
                    match.save(update_fields=['datetime'])
        except sender.DoesNotExist:
            pass
