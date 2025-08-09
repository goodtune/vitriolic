import pathlib

from django.db import migrations

migration_name = pathlib.Path(__file__).stem
forwards_sql_file = pathlib.Path(__file__).parent / f"{migration_name}.forwards.sql"
backwards_sql_file = pathlib.Path(__file__).parent / f"{migration_name}.backwards.sql"

with forwards_sql_file.open("r") as file:
    forwards_sql = file.read()

with backwards_sql_file.open("r") as file:
    backwards_sql = file.read()


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0050_alter_place_timezone_and_more"),
    ]

    operations = [migrations.RunSQL(forwards_sql, backwards_sql)]
