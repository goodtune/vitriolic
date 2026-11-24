import pytest
from django.db import connection

from harness.ownership import CHECKOUT, recorded_owner, refusal


def comment_on_database(text: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "DO $$ BEGIN EXECUTE format('COMMENT ON DATABASE %%I IS %%L', "
            "current_database(), %s::text); END $$",
            [text],
        )


@pytest.mark.django_db
def test_a_database_with_no_owner_is_refused():
    assert recorded_owner() == ""
    assert "nobody who left a name" in refusal()


@pytest.mark.django_db
def test_a_database_owned_by_this_checkout_is_accepted():
    comment_on_database(str(CHECKOUT))
    assert recorded_owner() == str(CHECKOUT)
    assert refusal() is None


@pytest.mark.django_db
def test_a_database_owned_by_another_checkout_is_refused_and_names_the_owner():
    comment_on_database("/somewhere/else")
    message = refusal()
    assert "belongs to /somewhere/else" in message
    assert str(CHECKOUT) in message
