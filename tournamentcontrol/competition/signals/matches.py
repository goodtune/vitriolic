import logging
from email.utils import formataddr

from django.conf import settings
from django.core.mail import send_mail
from django.template import Context, Template
from tournamentcontrol.competition.calc import BonusPointCalculator, Calculator
from tournamentcontrol.competition.signals.decorators import disable_for_loaddata
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
        logger.debug('BYE: Match #%s', instance.pk)
        return create_match_ladder_entries(instance)

    elif instance.is_forfeit:
        logger.debug('FORFEIT: Match #%s', instance.pk)
        return create_match_ladder_entries(instance)

    elif instance.home_team_score is not None and instance.away_team_score is not None:
        logger.debug('RESULT: Match #%s', instance.pk)
        return create_match_ladder_entries(instance)

    logger.debug('SKIPPED: Match #%s', instance.pk)


def match_deleted_handler(sender, instance, *args, **kwargs):
    """
    Function to be called prior to a Match being saved.

    This should remove the related LadderEntry objects for the match in
    question.
    """
    instance.ladder_entries.all().delete()


def create_match_ladder_entries(instance):
    home_ladder = create_team_ladder_entry(instance, 'home')
    away_ladder = create_team_ladder_entry(instance, 'away')
    return dict(home_ladder=home_ladder, away_ladder=away_ladder)


def create_team_ladder_entry(instance, home_or_away):
    from tournamentcontrol.competition.models import LadderEntry

    if home_or_away == 'home':
        opponent = 'away'
    elif home_or_away == 'away':
        opponent = 'home'

    team = getattr(instance, home_or_away + '_team', None)
    team_score = getattr(instance, home_or_away + '_team_score') or 0
    opponent_obj = getattr(instance, opponent + '_team', None)
    opponent_score = getattr(instance, opponent + '_team_score') or 0

    ladder_kwargs = dict(match_id=instance.pk,
                         played=1,
                         score_for=team_score,
                         score_against=opponent_score)

    if team is not None:
        ladder_kwargs['team_id'] = team.pk

    if opponent_obj is not None:
        ladder_kwargs['opponent_id'] = opponent_obj.pk

    if instance.is_bye:
        ladder_kwargs['bye'] = 1

    elif instance.is_forfeit:
        if not instance.stage.division.include_forfeits_in_played:
            ladder_kwargs['played'] = 0
        ladder_kwargs['forfeit_for'] = int(team == instance.forfeit_winner)
        ladder_kwargs['forfeit_against'] = int(team != instance.forfeit_winner)

    else:
        ladder_kwargs['win'] = int(team_score > opponent_score)
        ladder_kwargs['loss'] = int(team_score < opponent_score)
        ladder_kwargs['draw'] = int(team_score == opponent_score)

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

    context = Context({
        'match': match,
        'team': team,
    })

    # construct and send an email to the players in the opposition
    subject = Template("Your {{ match.time }} game against {{ team.title }} "
                       "has been forfeit").render(context)
    message = ""
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [formataddr((p.get_full_name(), p.email))
                      for p in participants]

    send_mail(subject, message, from_email, recipient_list)

    # construct and send an email to the competition administrators
    subject = Template("Forfeit: {{ match }} [{{ match.time }}, "
                       "{{ match.date }}, {{ match.play_at }}]").render(context)
    recipient_list = [formataddr((p.get_full_name(), p.email))
                      for p in administrators]

    send_mail(subject, message, from_email, recipient_list)
