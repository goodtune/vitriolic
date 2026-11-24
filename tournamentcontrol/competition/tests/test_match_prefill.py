"""
The live score offered as the result, and the scorers of the live score
events offered as the players' points: shown, marked as the scoreboard's, and
saved only when the operator saves.
"""

import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission
from django.utils import timezone
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import SuperUserFactory
from tournamentcontrol.competition.compops.sites import result_form
from tournamentcontrol.competition.forms import (
    MatchResultForm,
    MatchResultFormSet,
    MatchStatisticFormset,
)
from tournamentcontrol.competition.models import (
    Match,
    MatchEvent,
    SimpleScoreMatchStatistic,
)
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_compops_results import DATASTAR
from tournamentcontrol.competition.utils import FauxQueryset

TZ = ZoneInfo("Australia/Brisbane")
WHEN = timezone.make_aware(datetime.datetime(2026, 10, 8, 8), TZ)
MARK = "From the scoreboard"


def make_match(**kwargs):
    return factories.MatchFactory.create(
        datetime=WHEN, date=WHEN.date(), time=WHEN.time(), **kwargs
    )


class ResultFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.live = make_match(home_team_progress_score=3)
        cls.unscored = make_match()
        cls.finished = make_match(
            home_team_score=1, away_team_score=1, home_team_progress_score=4
        )

    def test_live_score_is_offered_and_marked(self):
        form = MatchResultForm(instance=self.live)
        self.assertEqual(
            (
                form["home_team_score"].value(),
                form["away_team_score"].value(),
                form.from_scoreboard,
            ),
            (3, 0, True),
        )

    def test_match_with_a_result_or_no_live_score_is_offered_nothing(self):
        for match, expected in (
            (self.finished, (1, 1, False)),
            (self.unscored, (None, None, False)),
        ):
            with self.subTest(match=match):
                form = MatchResultForm(instance=match)
                self.assertEqual(
                    (
                        form["home_team_score"].value(),
                        form["away_team_score"].value(),
                        form.from_scoreboard,
                    ),
                    expected,
                )

    def test_nothing_is_saved_until_the_offer_is_saved(self):
        MatchResultForm(instance=self.live)
        self.live.refresh_from_db()
        self.assertEqual(
            (self.live.home_team_score, self.live.away_team_score), (None, None)
        )

    def test_offer_saved_as_it_stands_is_saved_from_a_page_of_results(self):
        # A page of results saves only the forms that changed; the offer must
        # count as a change, or saving it as offered would save nothing.
        queryset = Match.objects.filter(pk=self.live.pk)
        offered = MatchResultFormSet(queryset=queryset, prefix="matches")
        data = {
            "matches-TOTAL_FORMS": "1",
            "matches-INITIAL_FORMS": "1",
            "matches-0-id": str(self.live.pk),
            "matches-0-home_team_score": offered.forms[0]["home_team_score"].value(),
            "matches-0-away_team_score": offered.forms[0]["away_team_score"].value(),
        }
        formset = MatchResultFormSet(data=data, queryset=queryset, prefix="matches")
        self.assertEqual(formset.is_valid(), True)
        formset.save()
        self.live.refresh_from_db()
        self.assertEqual((self.live.home_team_score, self.live.away_team_score), (3, 0))

    def test_ops_row_offers_the_live_score(self):
        form = result_form(self.live)
        self.assertEqual(form["home_team_score"].value(), 3)
        self.assertEqual(form.from_scoreboard, True)


@per_shell
class ResultsPageTests(TestCase):
    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.live = make_match(home_team_progress_score=3, away_team_progress_score=2)
        cls.season = cls.live.stage.division.season
        cls.superuser = cls.make_user("boss")

    def test_results_page_marks_the_live_score_it_offers(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:match-results",
                self.season.competition_id,
                self.season.pk,
                "20261008",
            )
        self.assertEqual(self.last_response.content.decode().count(MARK), 1)
        (form,) = self.get_context("match_formset").forms
        self.assertEqual(
            (form["home_team_score"].value(), form["away_team_score"].value()), (3, 2)
        )


class OpsResultsRowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = factories.UserFactory.create(is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(codename="change_match"))
        season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
        )
        cls.live = make_match(
            stage__division__season=season,
            home_team_progress_score=3,
            away_team_progress_score=2,
        )

    def test_row_offers_and_marks_the_live_score(self):
        with self.login(self.staff):
            self.get(
                "compops:slot",
                competition="pacific-cup",
                season="pc26",
                datestr="20261008",
                slot_key="0800",
            )
        self.assertResponseContains(
            '<input type="number" name="home_team_score" value="3" class="sc" '
            'data-preserve-attr="value" data-from-scoreboard '
            f'id="m{self.live.pk}_home_team_score">'
        )
        self.assertResponseContains(f'<span class="pill">{MARK}</span>')


class StatisticsFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.match = make_match(home_team_score=2, away_team_score=1)
        cls.seven = cls.player(cls.match.home_team, 7)
        cls.nine = cls.player(cls.match.home_team, 9)
        cls.four = cls.player(cls.match.away_team, 4)
        for side, person in (("home", cls.seven), ("home", cls.seven)):
            cls.match.record_event(MatchEvent.Kind.SCORE, side, player=person)
        cls.match.record_event(MatchEvent.Kind.SCORE, "home")
        taken_back = cls.match.record_event(
            MatchEvent.Kind.SCORE, "away", player=cls.four
        )
        cls.match.reverse_event(taken_back)

    @staticmethod
    def player(team, number):
        return factories.TeamAssociationFactory.create(
            team=team, number=number, is_player=True
        ).person


class StatisticsFormsetTests(StatisticsFixture):
    def roster(self, team):
        stats = FauxQueryset(SimpleScoreMatchStatistic, team=team)
        for association in team.people.filter(is_player=True):
            stats.append(
                SimpleScoreMatchStatistic(
                    match=self.match,
                    player=association.person,
                    number=association.number,
                    played=1,
                )
            )
        return stats

    def test_scorers_named_in_the_live_score_are_offered_their_points(self):
        self.assertEqual(self.match.scoreboard_points(), {self.seven.pk: 2})
        formset = MatchStatisticFormset(
            2,
            prefix="home",
            queryset=self.roster(self.match.home_team),
            live_points=self.match.scoreboard_points(),
        )
        self.assertEqual(
            {form.instance.player: form["points"].value() for form in formset},
            {self.seven: 2, self.nine: None},
        )
        self.assertEqual(formset.from_scoreboard, True)
        self.assertEqual(SimpleScoreMatchStatistic.objects.count(), 0)

    def test_match_with_statistics_is_offered_nothing(self):
        factories.SimpleScoreMatchStatisticFactory.create(
            match=self.match, player=self.nine, points=2, played=1
        )
        self.assertEqual(self.match.scoreboard_points(), {})


@per_shell
class StatisticsPageTests(StatisticsFixture):
    user_factory = SuperUserFactory

    def test_statistics_page_marks_the_points_it_offers(self):
        with self.login(self.make_user("boss")):
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:match:detail",
                *self.match._get_url_args(),
            )
        self.assertEqual(self.last_response.content.decode().count(MARK), 1)
        (home, away) = self.get_context("formsets")
        self.assertEqual([form["points"].value() for form in home], [2, None])


class OpsScorersModalTests(StatisticsFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        season = cls.match.stage.division.season
        season.slug, season.slug_locked = "pc26", True
        season.timezone = "Australia/Brisbane"
        season.statistics = True
        season.save()
        competition = season.competition
        competition.slug, competition.slug_locked = "pacific-cup", True
        competition.save()
        cls.staff = factories.UserFactory.create(is_staff=True)
        cls.staff.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "add_simplescorematchstatistic",
                    "change_simplescorematchstatistic",
                ]
            )
        )

    def test_modal_offers_and_marks_the_points(self):
        with self.login(self.staff):
            self.get(
                "compops:match-scorers",
                competition="pacific-cup",
                season="pc26",
                datestr="20261008",
                match_pk=self.match.pk,
                extra=DATASTAR,
            )
        body = b"".join(self.last_response.streaming_content).decode()
        self.assertEqual(body.count(MARK), 1)
        self.assertIn('name="home-0-points" value="2"', body)
