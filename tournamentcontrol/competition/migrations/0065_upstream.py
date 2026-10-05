# Generalise the MySideline link into an "upstream" link that any competition
# management provider can use. New columns are added and populated here; the
# MySideline columns they replace are dropped by 0066_remove_mysideline, in a
# separate migration because PostgreSQL will not alter a table whose rows were
# updated earlier in the same transaction while deferred constraint triggers
# are pending.

from urllib.parse import parse_qs, urlencode, urlparse

from django.db import migrations, models
from django.db.models import Value
from django.db.models.functions import Cast, Concat, Substr

MYSIDELINE_PREFIX = "mysideline:"


def forwards(apps, schema_editor):
    Season = apps.get_model("competition", "Season")
    for season in Season.objects.filter(
        mysideline_season__isnull=False,
        competition__mysideline_url__isnull=False,
    ).select_related("competition"):
        url = season.competition.mysideline_url
        if not url:
            continue
        params = {"season": season.mysideline_season}
        if season.mysideline_season_tag is not None:
            params["seasonTag"] = season.mysideline_season_tag
        Season.objects.filter(pk=season.pk).update(
            upstream_url="%s?%s" % (url, urlencode(params))
        )

    for model_name in ("Division", "Team", "Match"):
        model = apps.get_model("competition", model_name)
        model.objects.filter(mysideline_id__isnull=False).update(
            upstream_id=Concat(
                Value(MYSIDELINE_PREFIX),
                Cast("mysideline_id", output_field=models.CharField()),
            )
        )


def backwards(apps, schema_editor):
    Season = apps.get_model("competition", "Season")
    for season in Season.objects.filter(upstream_url__isnull=False):
        query = parse_qs(urlparse(season.upstream_url).query)
        try:
            year = int(query["season"][0])
        except (KeyError, IndexError, ValueError):
            continue
        tag = None
        try:
            tag = int(query["seasonTag"][0])
        except (KeyError, IndexError, ValueError):
            pass
        Season.objects.filter(pk=season.pk).update(
            mysideline_season=year, mysideline_season_tag=tag
        )

    for model_name in ("Division", "Team", "Match"):
        model = apps.get_model("competition", model_name)
        model.objects.filter(upstream_id__startswith=MYSIDELINE_PREFIX).update(
            mysideline_id=Cast(
                Substr("upstream_id", len(MYSIDELINE_PREFIX) + 1),
                output_field=models.BigIntegerField(),
            )
        )


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0064_mysideline_titles"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="upstream_url",
            field=models.URLField(
                blank=True,
                help_text=(
                    "The page on the provider that lists this season's draws: the "
                    "association page filtered to a year on MySideline (for example "
                    "https://tfa.mysideline.com.au/competitions/association/6338"
                    "?season=2026&seasonTag=2) or a competition's draws page on "
                    "revolutioniseSPORT (https://www.revolutionise.com.au/ccha/games/25527). "
                    "Required for synchronisation when the competition has an upstream URL."
                ),
                max_length=1024,
                null=True,
                verbose_name="Upstream URL",
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="upstream_id",
            field=models.CharField(
                blank=True, editable=False, max_length=255, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="upstream_id",
            field=models.CharField(
                blank=True, editable=False, max_length=255, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="upstream_id",
            field=models.CharField(
                blank=True, editable=False, max_length=255, null=True, unique=True
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
