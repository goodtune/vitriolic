from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0055_remove_ranking_fkey_constraints"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="season",
            name="live_stream_thumbnail",
        ),
        migrations.RemoveField(
            model_name="match",
            name="live_stream_thumbnail",
        ),
    ]