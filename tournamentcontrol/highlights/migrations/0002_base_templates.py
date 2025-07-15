# -*- coding: utf-8 -*-
from django.db import migrations


def load_templates(apps, schema_editor):
    BaseTemplate = apps.get_model("highlights", "BaseTemplate")

    templates = [
        {
            "name": "Match score",
            "slug": "match-score",
            "template_type": "match_score",
            "svg": """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"450\">\n    <rect width=\"800\" height=\"450\" fill=\"{{ background_color }}\"/>\n    <text x=\"400\" y=\"60\" font-size=\"40\" text-anchor=\"middle\" fill=\"{{ text_color }}\">{{ competition }}</text>\n    <text x=\"400\" y=\"110\" font-size=\"30\" text-anchor=\"middle\" fill=\"{{ text_color }}\">{{ match_date }}</text>\n    <text x=\"200\" y=\"220\" font-size=\"100\" text-anchor=\"middle\" fill=\"{{ primary_color }}\">{{ home_score }}</text>\n    <text x=\"600\" y=\"220\" font-size=\"100\" text-anchor=\"middle\" fill=\"{{ primary_color }}\">{{ away_score }}</text>\n    <text x=\"200\" y=\"320\" font-size=\"40\" text-anchor=\"middle\" fill=\"{{ text_color }}\">{{ home_team }}</text>\n    <text x=\"600\" y=\"320\" font-size=\"40\" text-anchor=\"middle\" fill=\"{{ text_color }}\">{{ away_team }}</text>\n</svg>""",
        },
        {
            "name": "Ground day schedule",
            "slug": "ground-day-schedule",
            "template_type": "ground_day",
            "svg": """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"600\">\n    <rect width=\"800\" height=\"600\" fill=\"{{ background_color }}\"/>\n    <text x=\"400\" y=\"60\" font-size=\"40\" text-anchor=\"middle\" fill=\"{{ text_color }}\">{{ ground }} - {{ date }}</text>\n    <!-- Add match details here -->\n</svg>""",
        },
        {
            "name": "Team schedule",
            "slug": "team-schedule",
            "template_type": "team_schedule",
            "svg": """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"600\">\n    <rect width=\"800\" height=\"600\" fill=\"{{ background_color }}\"/>\n    <text x=\"400\" y=\"60\" font-size=\"40\" text-anchor=\"middle\" fill=\"{{ text_color }}\">{{ team_name }} Schedule</text>\n    <!-- Add match list details here -->\n</svg>""",
        },
    ]

    for data in templates:
        BaseTemplate.objects.update_or_create(slug=data["slug"], defaults=data)


def unload_templates(apps, schema_editor):
    BaseTemplate = apps.get_model("highlights", "BaseTemplate")
    BaseTemplate.objects.filter(
        slug__in=["match-score", "ground-day-schedule", "team-schedule"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("highlights", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_templates, reverse_code=unload_templates),
    ]
