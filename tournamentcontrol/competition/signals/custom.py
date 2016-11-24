from django.dispatch import Signal

match_forfeit = Signal(providing_args=["match", "team"])
score_updated = Signal(providing_args=["match"])
