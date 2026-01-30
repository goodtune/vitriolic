# Migration to add color fields to Division and Stage models

from django.core import validators
from django.db import migrations, models
import tournamentcontrol.competition.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0056_remove_ranking_tables_and_fields"),
    ]

    operations = [
        # Add Division color field (not null, with callable default)
        migrations.AddField(
            model_name="division",
            name="color",
            field=models.CharField(
                default=tournamentcontrol.competition.models.generate_random_color,
                help_text="Color for division in the visual scheduler. Affects the left border of match cards and division headers.",
                max_length=7,
                verbose_name="Color",
                validators=[
                    validators.RegexValidator(
                        regex=r'^#[0-9a-fA-F]{6}$',
                        message='Enter a valid hex color code (e.g., #ff5733)',
                    )
                ],
            ),
        ),
        # Add Stage color field (not null, with db_default)
        migrations.AddField(
            model_name="stage",
            name="color",
            field=models.CharField(
                db_default="#e8f5e8",
                help_text="Background color for matches in the visual scheduler. Used to highlight matches of increased importance.",
                max_length=7,
                verbose_name="Background Color",
                validators=[
                    validators.RegexValidator(
                        regex=r'^#[0-9a-fA-F]{6}$',
                        message='Enter a valid hex color code (e.g., #ff5733)',
                    )
                ],
            ),
        ),
        # Add database-level CHECK constraints for color validation
        migrations.AddConstraint(
            model_name="division",
            constraint=models.CheckConstraint(
                condition=models.Q(color__regex=r'^#[0-9a-fA-F]{6}$'),
                name='division_color_valid_hex',
            ),
        ),
        migrations.AddConstraint(
            model_name="stage",
            constraint=models.CheckConstraint(
                condition=models.Q(color__regex=r'^#[0-9a-fA-F]{6}$'),
                name='stage_color_valid_hex',
            ),
        ),
    ]
