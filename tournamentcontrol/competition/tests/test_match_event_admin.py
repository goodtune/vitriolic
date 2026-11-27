"""
A match's event log in the admin: listed on the match's page, added to, and
put right with a correction. Nothing deletes an event.
"""

from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import StaffFactory
from tournamentcontrol.competition.models import Match, MatchEvent
from tournamentcontrol.competition.tests import factories

PREFIX = "admin:fixja:competition:season:division:stage:match"


@per_shell
class MatchEventAdminTests(TestCase):
    user_factory = StaffFactory

    @classmethod
    def setUpTestData(cls):
        cls.match = factories.MatchFactory.create(
            home_team__title="Australia", away_team__title="New Zealand"
        )
        cls.home_player = cls.player(cls.match.home_team, "Jo", "Home")
        cls.away_player = cls.player(cls.match.away_team, "Sam", "Away")
        cls.coach = factories.TeamAssociationFactory.create(
            team=cls.match.home_team, is_player=False
        ).person
        cls.stranger = factories.TeamAssociationFactory.create().person
        cls.keeper = cls.make_user(
            "keeper",
            perms=[
                "competition.add_matchevent",
                "competition.change_matchevent",
                "competition.change_match",
            ],
        )
        cls.viewer = cls.make_user("viewer", perms=["competition.change_match"])

    @staticmethod
    def player(team, first_name, last_name):
        return factories.TeamAssociationFactory.create(
            team=team,
            is_player=True,
            person__first_name=first_name,
            person__last_name=last_name,
        ).person

    def args(self, *extra):
        return (*self.match._get_url_args(), *extra)

    def progress(self):
        self.match.refresh_from_db()
        return (
            self.match.home_team_progress_score,
            self.match.away_team_progress_score,
        )

    def test_event_has_an_address_to_edit_and_to_correct_it_and_none_to_delete(self):
        event = self.match.record_event(MatchEvent.Kind.START)
        self.assertCountEqual(event.urls, ["add", "edit", "reverse"])

    def test_pages_need_a_login(self):
        event = self.match.record_event(MatchEvent.Kind.START)
        for name, extra in (("add", ()), ("edit", (event.pk,))):
            with self.subTest(name=name):
                self.assertLoginRequired(
                    f"{PREFIX}:matchevent:{name}", *self.args(*extra)
                )

    def test_match_page_lists_its_events(self):
        scored = self.match.record_event(
            MatchEvent.Kind.SCORE, "home", player=self.home_player
        )
        self.match.reverse_event(scored)
        with self.login(self.keeper):
            self.get_check_200(f"{PREFIX}:edit", *self.args())
        content = self.last_response.content.decode()
        add = self.reverse(f"{PREFIX}:matchevent:add", *self.args())
        self.assertIn(f'href="{add}"', content)
        self.assertIn(">Score · Australia</a>", content)
        self.assertIn("Home, Jo", content)
        self.assertIn(">Correction · Australia</a>", content)

    def test_add_offers_the_players_of_the_two_teams_only(self):
        with self.login(self.keeper):
            self.get_check_200(f"{PREFIX}:matchevent:add", *self.args())
        form = self.get_context("form")
        self.assertCountEqual(
            form.fields["player"].queryset, [self.home_player, self.away_player]
        )
        self.assertEqual(
            [value for value, label in form.fields["kind"].choices],
            ["", "start", "score", "dismissal"],
        )

    def test_add_records_a_score_and_counts_it(self):
        with self.login(self.keeper):
            self.post(
                f"{PREFIX}:matchevent:add",
                *self.args(),
                data={"kind": "score", "side": "away", "player": self.away_player.pk},
            )
        self.assert_http_302_found(url=f"{self.match.urls['edit']}#events-tab")
        event = self.match.events.get()
        self.assertEqual(
            (event.kind, event.side, event.points, event.player, event.recorded_by),
            ("score", "away", 1, self.away_player, self.keeper),
        )
        self.assertEqual(self.progress(), (None, 1))

    def test_add_refuses_a_score_of_neither_team_or_by_the_other_teams_player(self):
        cases = (
            ({"kind": "score", "side": ""}, "side"),
            (
                {"kind": "score", "side": "home", "player": self.away_player.pk},
                "player",
            ),
            ({"kind": "score", "side": "home", "player": self.coach.pk}, "player"),
            ({"kind": "correction", "side": "home"}, "kind"),
        )
        for data, field in cases:
            with self.subTest(data=data), self.login(self.keeper):
                self.post(f"{PREFIX}:matchevent:add", *self.args(), data=data)
                self.assert_http_200_ok()
                self.assertEqual(list(self.get_context("form").errors), [field])
        self.assertEqual(self.match.events.count(), 0)

    def test_edit_changes_only_who_scored_from_the_sides_players(self):
        event = self.match.record_event(MatchEvent.Kind.SCORE, "home")
        with self.login(self.keeper):
            self.get_check_200(f"{PREFIX}:matchevent:edit", *self.args(event.pk))
            form = self.get_context("form")
            self.assertEqual(list(form.fields), ["player"])
            self.assertCountEqual(form.fields["player"].queryset, [self.home_player])
            self.post(
                f"{PREFIX}:matchevent:edit",
                *self.args(event.pk),
                data={"player": self.home_player.pk},
            )
        self.assert_http_302_found(url=f"{self.match.urls['edit']}#events-tab")
        event.refresh_from_db()
        self.assertEqual((event.player, event.points), (self.home_player, 1))
        self.assertEqual(self.progress(), (1, None))

    def test_correcting_reverses_the_event_and_takes_its_points_off(self):
        event = self.match.record_event(MatchEvent.Kind.SCORE, "home")
        with self.login(self.keeper):
            self.post(f"{PREFIX}:matchevent:reverse", *self.args(event.pk))
        self.assert_http_302_found(url=f"{self.match.urls['edit']}#events-tab")
        correction = self.match.events.get(kind=MatchEvent.Kind.CORRECTION)
        self.assertEqual(
            (correction.reverses, correction.recorded_by), (event, self.keeper)
        )
        self.assertEqual(self.progress(), (0, None))
        # A correction, or an event already reversed, cannot be corrected.
        for target in (event, correction):
            with self.subTest(target=target), self.login(self.keeper):
                self.post(f"{PREFIX}:matchevent:reverse", *self.args(target.pk))
                self.assert_http_400_bad_request()
        self.assertEqual(self.match.events.count(), 2)

    def test_correcting_needs_a_post_and_the_permission(self):
        event = self.match.record_event(MatchEvent.Kind.SCORE, "home")
        with self.login(self.keeper):
            self.get(f"{PREFIX}:matchevent:reverse", *self.args(event.pk))
        self.assert_http_405_method_not_allowed()
        with self.login(self.viewer):
            self.post(f"{PREFIX}:matchevent:reverse", *self.args(event.pk))
            self.assert_http_403_forbidden()
            self.post(f"{PREFIX}:matchevent:add", *self.args(), data={"kind": "start"})
            self.assert_http_403_forbidden()
        self.assertEqual(self.match.events.count(), 1)
        self.assertEqual(self.progress(), (1, None))

    def test_event_of_another_match_is_not_found_through_this_one(self):
        other = factories.MatchFactory.create(stage=self.match.stage)
        event = other.record_event(MatchEvent.Kind.SCORE, "home")
        with self.login(self.keeper):
            self.get(f"{PREFIX}:matchevent:edit", *self.args(event.pk))
            self.assert_http_404_not_found()
            self.post(f"{PREFIX}:matchevent:reverse", *self.args(event.pk))
            self.assert_http_404_not_found()
        self.assertEqual(Match.objects.get(pk=other.pk).home_team_progress_score, 1)
