from email.utils import formataddr

from django.conf import settings
from django.core.mail import send_mail
from django.template import Context, Template
from django.dispatch import receiver

from tournamentcontrol.competition.events import match_forfeit
from tournamentcontrol.competition.utils import forfeit_notification_recipients


@receiver(match_forfeit)
def notify_match_forfeit_email(sender, match, team, **kwargs):
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
