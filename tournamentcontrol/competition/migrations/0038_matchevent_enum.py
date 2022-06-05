# Generated by Django 3.2.13 on 2022-06-05 22:13

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0037_matchevent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="matchevent",
            name="type",
            field=models.TextField(
                choices=[
                    ("Coin Toss", "Toss"),
                    ("Timing Event", "Time"),
                    ("Scoring Event", "Score"),
                    ("Discipline Event", "Discipline"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
