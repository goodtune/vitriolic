# Generated manually

from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0055_remove_ranking_fkey_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="logo_colour",
            field=models.ImageField(
                blank=True,
                help_text="Colour variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/competition/colour/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="competition",
            name="logo_monochrome",
            field=models.ImageField(
                blank=True,
                help_text="Monochrome variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/competition/monochrome/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="club",
            name="logo_colour",
            field=models.ImageField(
                blank=True,
                help_text="Colour variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/club/colour/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="club",
            name="logo_monochrome",
            field=models.ImageField(
                blank=True,
                help_text="Monochrome variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/club/monochrome/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="season",
            name="logo_colour",
            field=models.ImageField(
                blank=True,
                help_text="Colour variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/season/colour/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="season",
            name="logo_monochrome",
            field=models.ImageField(
                blank=True,
                help_text="Monochrome variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/season/monochrome/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="logo_colour",
            field=models.ImageField(
                blank=True,
                help_text="Colour variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/division/colour/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="logo_monochrome",
            field=models.ImageField(
                blank=True,
                help_text="Monochrome variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/division/monochrome/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="logo_colour",
            field=models.ImageField(
                blank=True,
                help_text="Colour variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/team/colour/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="logo_monochrome",
            field=models.ImageField(
                blank=True,
                help_text="Monochrome variant of the logo. Recommended: PNG, JPG, or SVG format with square (1:1) aspect ratio.",
                null=True,
                upload_to="logos/team/monochrome/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["png", "jpg", "jpeg", "svg"]
                    )
                ],
            ),
        ),
    ]
