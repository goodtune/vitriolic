from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("competition", "0073_unique_team_order")]

    operations = [
        migrations.AlterModelOptions(
            name="season",
            options={
                "ordering": ("order",),
                "permissions": [
                    ("stream_season", "Can start and stop live streams for the season"),
                    (
                        "commentate_season",
                        "Can watch the commentary booths of the season",
                    ),
                ],
            },
        ),
    ]
