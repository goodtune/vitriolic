import logging
from email.utils import formataddr
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.template import Context, Template
from django.template.loader import render_to_string
from django.urls import reverse
from googleapiclient.errors import HttpError

from tournamentcontrol.competition.calc import BonusPointCalculator, Calculator
from tournamentcontrol.competition.signals.decorators import (
    disable_for_loaddata,
)
from tournamentcontrol.competition.utils import forfeit_notification_recipients

logger = logging.getLogger(__name__)


@disable_for_loaddata
def match_saved_handler(sender, instance, created, *args, **kwargs):
    """
    Function to be called following a Match being saved.

    This should create the necessary LadderEntry objects for the match in
    question (by deleting previous entries) and inserting new values.
    """
    for ladder_entry in instance.ladder_entries.all():
        ladder_entry.delete()

    if instance.is_bye and instance.bye_processed:
        logger.debug("BYE: Match #%s", instance.pk)
        return create_match_ladder_entries(instance)

    elif instance.is_forfeit:
        logger.debug("FORFEIT: Match #%s", instance.pk)
        return create_match_ladder_entries(instance)

    elif instance.home_team_score is not None and instance.away_team_score is not None:
        logger.debug("RESULT: Match #%s", instance.pk)
        return create_match_ladder_entries(instance)

    logger.debug("SKIPPED: Match #%s", instance.pk)


def match_deleted_handler(sender, instance, *args, **kwargs):
    """
    Function to be called prior to a Match being saved.

    This should remove the related LadderEntry objects for the match in
    question.
    """
    instance.ladder_entries.all().delete()


def create_match_ladder_entries(instance):
    home_ladder = create_team_ladder_entry(instance, "home")
    away_ladder = create_team_ladder_entry(instance, "away")
    return dict(home_ladder=home_ladder, away_ladder=away_ladder)


def create_team_ladder_entry(instance, home_or_away):
    from tournamentcontrol.competition.models import LadderEntry

    if home_or_away == "home":
        opponent = "away"
    elif home_or_away == "away":
        opponent = "home"

    team = getattr(instance, home_or_away + "_team", None)
    team_score = getattr(instance, home_or_away + "_team_score") or 0
    opponent_obj = getattr(instance, opponent + "_team", None)
    opponent_score = getattr(instance, opponent + "_team_score") or 0

    ladder_kwargs = dict(
        match_id=instance.pk,
        played=1,
        score_for=team_score,
        score_against=opponent_score,
    )

    if team is not None:
        ladder_kwargs["team_id"] = team.pk

    if opponent_obj is not None:
        ladder_kwargs["opponent_id"] = opponent_obj.pk

    if instance.is_bye:
        ladder_kwargs["bye"] = 1

    elif instance.is_forfeit:
        if not instance.stage.division.include_forfeits_in_played:
            ladder_kwargs["played"] = 0
        ladder_kwargs["forfeit_for"] = int(team == instance.forfeit_winner)
        ladder_kwargs["forfeit_against"] = int(team != instance.forfeit_winner)

    else:
        ladder_kwargs["win"] = int(team_score > opponent_score)
        ladder_kwargs["loss"] = int(team_score < opponent_score)
        ladder_kwargs["draw"] = int(team_score == opponent_score)

    if team is not None:
        ladder = LadderEntry(**ladder_kwargs)

        calculator = Calculator(ladder)
        calculator.parse(instance.stage.division.points_formula)
        ladder.points = calculator.evaluate()

        if instance.stage.division.bonus_points_formula:
            bonus_calculator = BonusPointCalculator(ladder)
            bonus_calculator.parse(instance.stage.division.bonus_points_formula)
            ladder.bonus_points = bonus_calculator.evaluate()

        ladder.points += ladder.bonus_points
        ladder.save()

        return ladder


def notify_match_forfeit_email(sender, match, team, *args, **kwargs):
    """
    When a match is notified as having been forfeit, send a notification email
    to players in the opposition team and the designated season administrators.

    :param match: the match that was forfeit
    :param team: the team that forfeit the match
    :return: None
    """
    participants, administrators = forfeit_notification_recipients(match)

    context = Context(
        {
            "match": match,
            "team": team,
        }
    )

    # construct and send an email to the players in the opposition
    subject = Template(
        "Your {{ match.time }} game against {{ team.title }} has been forfeit"
    ).render(context)
    message = ""
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [formataddr((p.get_full_name(), p.email)) for p in participants]

    send_mail(subject, message, from_email, recipient_list)

    # construct and send an email to the competition administrators
    subject = Template(
        "Forfeit: {{ match }} [{{ match.time }}, {{ match.date }}, {{ match.play_at }}]"
    ).render(context)
    recipient_list = [formataddr((p.get_full_name(), p.email)) for p in administrators]

    send_mail(subject, message, from_email, recipient_list)


@disable_for_loaddata
def match_youtube_sync(sender, instance, **kwargs):
    """
    Handle YouTube live stream updates when a Match is saved.

    This signal handler replaces the pre_save_callback in the edit_match admin view
    to decouple YouTube operations from the request/response cycle.
    """
    from tournamentcontrol.competition.tasks import set_youtube_thumbnail

    obj = instance
    
    # Check if YouTube credentials are configured before attempting anything else,
    # we can't interact with the YouTube API without them.
    season = obj.stage.division.season
    if not (season.live_stream_client_id and season.live_stream_client_secret):
        return

    competition = season.competition
    division = obj.stage.division
    stage = obj.stage

    # Build match video URL for description using Site model
    # Only build the URL if the match has been saved and has a primary key
    current_site = Site.objects.get_current()
    if obj.pk:
        match_path = reverse(
            'competition:match-video',
            kwargs={
                'competition': competition.slug,
                'season': season.slug,
                'division': division.slug,
                'match': obj.pk,
            }
        )
        match_url = f"https://{current_site.domain}{match_path}"
    else:
        # For new objects without a PK yet, use the competition main page as fallback
        competition_path = reverse(
            'competition:competition',
            kwargs={
                'competition': competition.slug,
            }
        )
        match_url = f"https://{current_site.domain}{competition_path}"

    # Create context for template rendering
    template_context = {
        "match": obj,
        "competition": competition,
        "season": season,
        "division": division,
        "stage": stage,
        "match_url": match_url,
    }

    # Render title from template with hierarchical fallback
    title_templates = [
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/{competition.slug}/match/live_stream/title.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/match/live_stream/title.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/match/live_stream/title.txt",
        f"tournamentcontrol/competition/{stage.slug}/match/live_stream/title.txt",
        "tournamentcontrol/competition/match/live_stream/title.txt",
    ]
    title = render_to_string(title_templates, template_context).strip()

    # Render description from template with hierarchical fallback
    description_templates = [
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/{competition.slug}/match/live_stream/description.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/match/live_stream/description.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/match/live_stream/description.txt",
        f"tournamentcontrol/competition/{stage.slug}/match/live_stream/description.txt",
        "tournamentcontrol/competition/match/live_stream/description.txt",
    ]
    description = render_to_string(description_templates, template_context).strip()

    start_time = obj.get_datetime(ZoneInfo("UTC"))

    # Skip YouTube API interaction if we don't have valid start time
    # This can happen for new matches that don't have complete date/time data
    if start_time is None:
        return

    stop_time = start_time + relativedelta(minutes=50)  # FIXME: hard coded

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "scheduledStartTime": start_time.isoformat(),
            "scheduledEndTime": stop_time.isoformat(),
        },
        "status": {
            "privacyStatus": season.live_stream_privacy,
            "selfDeclaredMadeForKids": False,
        },
        "contentDetails": {
            "enableAutoStart": False,
            "enableAutoStop": False,
            "monitorStream": {
                "broadcastStreamDelayMs": 0,
                "enableMonitorStream": True,
            },
        },
    }

    try:
        if obj.external_identifier:
            # If we have disabled live-streaming where it was previously
            # enabled, we need to remove it using the YouTube API.
            if not obj.live_stream:
                video_id = obj.external_identifier
                season.youtube.liveBroadcasts().delete(id=video_id).execute()
                if obj.videos is not None:
                    obj.videos.remove(f"https://youtu.be/{video_id}")
                if not obj.videos:
                    obj.videos = None
                obj.external_identifier = None
                logger.info("YouTube video %r deleted", video_id)
                return

            # Alternatively we're making sure the representation on the backend
            # is consistent with the current status.
            else:
                body["id"] = obj.external_identifier
                broadcast = (
                    season.youtube.liveBroadcasts()
                    .update(part="snippet,status,contentDetails", body=body)
                    .execute()
                )
                set_youtube_thumbnail.s(obj.pk).apply_async(countdown=10)
                logger.info("YouTube video %r updated", broadcast)

        # If we have enabled live-streaming, but don't have an external id, we
        # need to create an event with the YouTube API and store the external
        # id.
        elif obj.live_stream:
            broadcast = (
                season.youtube.liveBroadcasts()
                .insert(
                    part="id,snippet,status,contentDetails",
                    body=body,
                )
                .execute()
            )
            obj.external_identifier = broadcast["id"]
            set_youtube_thumbnail.s(obj.pk).apply_async(countdown=10)
            video_link = f"https://youtu.be/{obj.external_identifier}"
            if obj.videos is None:
                obj.videos = [video_link]
            else:
                obj.videos.append(video_link)
            logger.info("YouTube video %r inserted", broadcast)

        # We need to bind to a liveStream resource. This is only supported on
        # a Ground, not a Venue. Only attempt binding if external_identifier exists.
        if (obj.external_identifier and obj.play_at and 
            hasattr(obj.play_at, 'ground') and obj.play_at.ground.external_identifier):
            bind = (
                season.youtube.liveBroadcasts()
                .bind(
                    part="id,snippet,contentDetails,status",
                    id=obj.external_identifier,
                    streamId=obj.play_at.ground.external_identifier,
                )
                .execute()
            )
            obj.live_stream_bind = bind["contentDetails"].get("boundStreamId")

    except HttpError as exc:
        logger.error("YouTube API error: %s", exc.reason)
        # Without access to the request/response cycle, we can't add messages
        # to the user interface, so we just log the error
        raise
    except Exception as exc:
        # Catch other exceptions (e.g., authentication errors) and log them
        # rather than crashing. This allows matches to be saved even when
        # YouTube API credentials are invalid or the API is unavailable.
        logger.error("Error syncing match to YouTube: %s", exc)
        # Don't re-raise - allow the match save to complete
