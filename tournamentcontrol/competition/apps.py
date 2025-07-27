"""[User Facing] Django app configuration for competition logic."""

from django.apps import AppConfig
from django.db.models.signals import (
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)


class CompetitionConfig(AppConfig):
    """Connects signals and admin components for competitions."""

    name = "tournamentcontrol.competition"

    def ready(self):
        """Wire up signal handlers and admin registration."""
        from touchtechnology.admin.sites import site
        from touchtechnology.content import utils
        from tournamentcontrol.competition.admin import (
            CompetitionAdminComponent,
        )
        from tournamentcontrol.competition.models import (
            Club,
            Competition,
            Division,
            Ground,
            LadderEntry,
            LadderSummary,
            Match,
            Season,
            Stage,
            StageGroup,
            Team,
            Venue,
        )
        from tournamentcontrol.competition.signals import (
            capture_timezone_before_save,
            changed_points_formula,
            delete_related,
            delete_team,
            match_forfeit,
            match_saved_handler,
            notify_match_forfeit_email,
            scale_ladder_entry,
            set_ground_latlng,
            set_ground_timezone,
            team_ladder_entry_aggregation,
            update_match_datetimes_on_place_timezone_change,
        )

        site.register(CompetitionAdminComponent)

        post_save.connect(match_saved_handler, sender=Match)

        pre_save.connect(scale_ladder_entry, sender=LadderSummary)
        post_save.connect(team_ladder_entry_aggregation, sender=LadderEntry)
        post_delete.connect(team_ladder_entry_aggregation, sender=LadderEntry)

        post_save.connect(set_ground_latlng, sender=Ground)
        post_save.connect(set_ground_timezone, sender=Ground)

        # Capture timezone before save to detect changes
        pre_save.connect(capture_timezone_before_save, sender=Venue)
        pre_save.connect(capture_timezone_before_save, sender=Ground)

        # Update match datetimes when timezone changes
        post_save.connect(update_match_datetimes_on_place_timezone_change, sender=Venue)
        post_save.connect(
            update_match_datetimes_on_place_timezone_change, sender=Ground
        )

        post_save.connect(changed_points_formula, sender=Division)

        pre_delete.connect(delete_team, sender=Team)

        # Anything with a slug should also force the sitemap url cache to be purged
        post_save.connect(utils.invalidate_sitemapnode_urlpatterns, sender=Competition)
        post_save.connect(utils.invalidate_sitemapnode_urlpatterns, sender=Season)
        post_save.connect(utils.invalidate_sitemapnode_urlpatterns, sender=Club)
        post_save.connect(utils.invalidate_sitemapnode_urlpatterns, sender=Division)
        post_save.connect(utils.invalidate_sitemapnode_urlpatterns, sender=Team)

        # Before deleting a match, delete it's LadderEntry and LadderSummary records
        pre_delete.connect(delete_related, sender=Competition)
        pre_delete.connect(delete_related, sender=Season)
        pre_delete.connect(delete_related, sender=Division)
        # pre_delete.connect(delete_related, sender=Team)
        pre_delete.connect(delete_related, sender=Match)
        pre_delete.connect(delete_related, sender=Stage)
        pre_delete.connect(delete_related, sender=StageGroup)

        # Connect our notification handlers
        match_forfeit.connect(notify_match_forfeit_email)
