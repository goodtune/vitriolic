import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0077_upstream_id_within_parent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MatchEvent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("start", "Start"),
                            ("score", "Score"),
                            ("dismissal", "Dismissal"),
                            ("correction", "Correction"),
                        ],
                        max_length=10,
                        verbose_name="Kind",
                    ),
                ),
                (
                    "side",
                    models.CharField(
                        blank=True,
                        choices=[("home", "Home"), ("away", "Away")],
                        max_length=4,
                        verbose_name="Team",
                    ),
                ),
                (
                    "points",
                    models.PositiveSmallIntegerField(default=0, verbose_name="Points"),
                ),
                (
                    "recorded_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, editable=False
                    ),
                ),
                (
                    "period",
                    models.PositiveSmallIntegerField(
                        blank=True, editable=False, null=True
                    ),
                ),
                (
                    "remaining",
                    models.PositiveIntegerField(blank=True, editable=False, null=True),
                ),
                (
                    "match",
                    touchtechnology.common.db.models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="competition.match",
                    ),
                ),
                (
                    "player",
                    touchtechnology.common.db.models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="competition.person",
                        verbose_name="Player",
                    ),
                ),
                (
                    "recorded_by",
                    touchtechnology.common.db.models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reverses",
                    models.OneToOneField(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="competition.matchevent",
                    ),
                ),
            ],
            options={
                "verbose_name": "match event",
                "verbose_name_plural": "match events",
                "ordering": ("recorded_at", "pk"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("kind", "correction"), ("reverses__isnull", False)
                        )
                        | models.Q(
                            models.Q(("kind", "correction"), _negated=True),
                            ("reverses__isnull", True),
                        ),
                        name="competition_matchevent_correction_reverses",
                    )
                ],
            },
        ),
    ]
