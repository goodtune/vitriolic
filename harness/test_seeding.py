import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db.models import F
from django.utils import timezone
from enrolment.models import SchoolYear
from freezegun import freeze_time

from harness.seeding import seed
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from touchtechnology.news.models import Article
from tournamentcontrol.competition.models import (
    Competition,
    Division,
    Match,
    Season,
    SeasonAssociation,
    StageGroup,
    UndecidedTeam,
    Venue,
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


@pytest.mark.django_db(transaction=True)
def test_seed_leaves_a_folder_and_an_application_node_in_the_site_tree():
    seed()
    folder = SitemapNode.objects.get(slug="archive")
    assert folder.content_type is None
    assert folder.parent.slug == "home"
    application = SitemapNode.objects.get(slug="latest-news")
    assert isinstance(application.object, Placeholder)
    assert application.object.path == "touchtechnology.news.sites.NewsSite"
    # The mount in tests/vitriolic/urls.py is at news/, so the node must not
    # take that slug.
    assert not SitemapNode.objects.filter(slug="news").exists()


@pytest.mark.django_db(transaction=True)
def test_seed_leaves_an_undecided_team_and_officials_in_the_current_season():
    first = seed()
    undecided = UndecidedTeam.objects.get()
    assert undecided.stage.title == "Finals"
    assert undecided.stage.division.season.title == "Spring 2026"
    officials = SeasonAssociation.objects.all()
    assert {o.season.title for o in officials} == {"Spring 2026"}
    assert officials.values("club").distinct().count() == 2
    for official in officials:
        assert official.person.club == official.club
        assert official.roles.exists()
    assert seed() == first
    assert UndecidedTeam.objects.count() == 1
    assert SeasonAssociation.objects.count() == officials.count()


@pytest.mark.django_db(transaction=True)
def test_seed_places_the_venues_at_round_invented_coordinates():
    seed()
    places = {
        (venue.title, round(float(venue.latitude), 4), round(float(venue.longitude), 4))
        for venue in Venue.objects.all()
    }
    assert places == {
        ("Anchor Park", -35.0, 150.0),
        ("Lantern Reserve", -35.01, 150.02),
    }
