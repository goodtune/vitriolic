import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0046_alter_match_live_stream_bind"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="live_stream_client_id",
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="live_stream_client_secret",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="live_stream_project_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="live_stream_refresh_token",
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="live_stream_scopes",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=200), null=True, size=None
            ),
        ),
        migrations.AddField(
            model_name="season",
            name="live_stream_token",
            field=models.CharField(max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="live_stream_token_uri",
            field=models.URLField(null=True),
        ),
    ]
