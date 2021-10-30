from __future__ import unicode_literals

import datetime

import factory
import factory.fuzzy
from django.contrib.auth import get_user_model
from django.utils import timezone
from factory.django import DjangoModelFactory
from tournamentcontrol.competition import models, utils


class SitemapNodeBaseFactory(DjangoModelFactory):
    """
    For any model which inherits from
    ``touchtechnology.common.models.SitemapNodeBase`` we need to execute the
    ``clean`` method which will populate the ``slug`` attribute according to
    the business logic of that method.
    """
    @factory.post_generation
    def post(obj, create, extracted, **kwargs):
        obj.clean()


class OrderedSitemapNodeFactory(SitemapNodeBaseFactory):
    """
    When adding a series of ``OrderedSitemapNode`` objects we should ensure
    that they are appropriately "ordered".
    """
    order = factory.Sequence(lambda n: (n + 1))


class RankDivisionFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.RankDivision

    title = factory.Sequence(lambda n: "Division %d" % n)


class ClubFactory(SitemapNodeBaseFactory):
    class Meta:
        model = models.Club

    title = factory.Faker('company')


class CompetitionFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.Competition

    title = factory.Sequence(lambda n: "Competition %d" % n)
    rank_importance = 1


class ClubRoleFactory(SitemapNodeBaseFactory):
    class Meta:
        model = models.ClubRole

    name = factory.Faker('company')
    competition = factory.SubFactory(CompetitionFactory)


class TeamRoleFactory(SitemapNodeBaseFactory):
    class Meta:
        model = models.TeamRole

    name = factory.Faker('company')
    competition = factory.SubFactory(CompetitionFactory)


class SeasonFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.Season

    title = factory.Sequence(
        lambda n: str(range(2015, 1900, -1)[n]))
    timezone = factory.Faker('timezone')

    competition = factory.SubFactory(CompetitionFactory)


class SeasonExclusionDateFactory(DjangoModelFactory):
    class Meta:
        model = models.SeasonExclusionDate

    date = factory.fuzzy.FuzzyDate(datetime.date(2013, 7, 15))
    season = factory.SubFactory(SeasonFactory)


class SeasonMatchTimeFactory(DjangoModelFactory):
    class Meta:
        model = models.SeasonMatchTime

    season = factory.SubFactory(SeasonFactory)

    start = factory.LazyAttribute(lambda o: datetime.time(o.count))
    interval = factory.fuzzy.FuzzyChoice([25, 30, 35, 40])
    count = factory.fuzzy.FuzzyChoice(range(1, 15))


class VenueFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.Venue

    title = factory.Sequence(lambda n: "Venue %d" % (n + 1))
    timezone = factory.SelfAttribute('season.timezone')

    season = factory.SubFactory(SeasonFactory)


class GroundFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.Ground

    title = factory.Sequence(lambda n: "Ground %d" % (n + 1))
    timezone = factory.SelfAttribute('venue.timezone')

    venue = factory.SubFactory(VenueFactory)


class DivisionFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.Division

    title = factory.Sequence(lambda n: "Division %d" % (n + 1))
    points_formula = "3*win + 2*draw + 1*loss"
    forfeit_for_score = 5
    forfeit_against_score = 0
    include_forfeits_in_played = True
    games_per_day = 2

    season = factory.SubFactory(SeasonFactory)


class DivisionExclusionDateFactory(DjangoModelFactory):
    class Meta:
        model = models.DivisionExclusionDate

    date = factory.fuzzy.FuzzyDate(datetime.date(2013, 7, 15))
    division = factory.SubFactory(DivisionFactory)


class TeamFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.Team

    title = factory.Sequence(lambda n: "Team %d" % (n + 1))

    club = factory.SubFactory(ClubFactory)
    division = factory.SubFactory(DivisionFactory)


class StageFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.Stage

    title = factory.Sequence(lambda n: "Stage %d" % (n + 1))

    division = factory.SubFactory(DivisionFactory)


class StageGroupFactory(OrderedSitemapNodeFactory):
    class Meta:
        model = models.StageGroup

    title = factory.Sequence(lambda n: "Pool %d" % (n + 1))

    stage = factory.SubFactory(StageFactory)


class UndecidedTeamFactory(DjangoModelFactory):
    class Meta:
        model = models.UndecidedTeam

    label = factory.Faker('text', max_nb_chars=30)
    stage = factory.SubFactory(StageFactory)


class MatchFactory(DjangoModelFactory):
    class Meta:
        model = models.Match

    stage = factory.SubFactory(StageFactory)

    home_team = factory.SubFactory(
        TeamFactory, division=factory.SelfAttribute('..stage.division'))
    away_team = factory.SubFactory(
        TeamFactory, division=factory.SelfAttribute('..stage.division'))

    datetime = factory.fuzzy.FuzzyDateTime(
        datetime.datetime(2008, 1, 1, tzinfo=timezone.utc))

    date = factory.LazyAttribute(lambda o: o.datetime.date())
    time = factory.LazyAttribute(lambda o: o.datetime.time())


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()

    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')

    username = factory.Sequence(lambda n: "user%04d" % (n + 1))
    email = factory.Sequence(lambda n: "user%03d@example.com" % (n + 1))

    password = 'crypt$$azoV33FJ2h3AA'  # pre-crypted "password"
    is_active = True


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = models.Person

    first_name = factory.SelfAttribute('user.first_name')
    last_name = factory.SelfAttribute('user.last_name')

    date_of_birth = factory.Faker(
        'date_time_between', start_date="-30y", end_date="-20y")
    gender = factory.fuzzy.FuzzyChoice(['M', 'F', 'X'])

    club = factory.SubFactory(ClubFactory)
    user = factory.SubFactory(UserFactory)


class ClubAssociationFactory(DjangoModelFactory):
    class Meta:
        model = models.ClubAssociation

    club = factory.SubFactory(ClubFactory)
    person = factory.SubFactory(PersonFactory)


class TeamAssociationFactory(DjangoModelFactory):
    class Meta:
        model = models.TeamAssociation

    team = factory.SubFactory(TeamFactory)
    person = factory.SubFactory(PersonFactory)


class DrawFormatFactory(DjangoModelFactory):
    class Meta:
        model = models.DrawFormat

    teams = factory.fuzzy.FuzzyChoice([4, 6, 8, 12])
    name = factory.LazyAttribute(
        lambda a: 'Round Robin ({}/{} teams)'.format(a.teams - 1, a.teams))
    text = factory.LazyAttribute(
        lambda a: utils.round_robin_format([t for t in range(1, a.teams + 1)]))
