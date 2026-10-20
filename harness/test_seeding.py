import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db.models import F
from django.utils import timezone
from enrolment.models import SchoolYear
from freezegun import freeze_time

from harness.seeding import seed
from touchtechnology.news.models import Article
from tournamentcontrol.competition.models import (
    Competition,
    Division,
    Match,
    Season,
    StageGroup,
)

User = get_user_model()


@pytest.mark.django_db(transaction=True)
def test_seed_is_idempotent():
    first = seed()
    second = seed()
    assert first == second
    assert Competition.objects.filter(slug="harbour-touch-league").count() == 1
    assert Season.objects.count() == 2
    assert Division.objects.count() == 6
    assert Match.objects.filter(is_forfeit=True).exists()
    assert Match.objects.filter(
        home_team_score=F("away_team_score"), home_team_score__isnull=False
    ).exists()
    assert Article.objects.count() == 5
    assert SchoolYear.objects.count() == 2
    assert User.objects.filter(username="admin", is_superuser=True).exists()


@pytest.mark.django_db(transaction=True)
def test_seed_on_a_later_day_adds_nothing():
    first = seed()
    with freeze_time(timezone.now() + datetime.timedelta(days=30)):
        second = seed()
    assert first == second
    assert Season.objects.filter(title="Spring 2026").count() == 1


@pytest.mark.django_db(transaction=True)
def test_seed_pools_one_division_and_plays_it_out():
    seed()
    pools = StageGroup.objects.all()
    assert pools.count() == 2
    assert {pool.stage.division.season.title for pool in pools} == {"Autumn 2026"}
    assert {pool.stage.division.title for pool in pools} == {"Mixed Open"}
    for pool in pools:
        assert pool.teams.count() == 3
    pool_matches = Match.objects.filter(stage_group__isnull=False, is_bye=False)
    assert pool_matches.count() == 6
    assert not pool_matches.filter(home_team_score__isnull=True).exists()
    assert not pool_matches.filter(away_team_score__isnull=True).exists()
    # The cross-pool finals went on to teams and were played.
    finals = Match.objects.filter(
        stage__division__title="Mixed Open",
        stage__division__season__title="Autumn 2026",
        stage__title="Finals",
    )
    assert finals.count() == 3
    assert not finals.filter(home_team__isnull=True).exists()
    assert not finals.filter(home_team_score__isnull=True).exists()
