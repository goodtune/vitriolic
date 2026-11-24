"""
The scorer's page and the venue's timekeeper write the match's event log: a
score, a correction, a start. The scoreboard itself is tested in
``test_compops_scoreboard``.
"""

from freezegun import freeze_time

from tournamentcontrol.competition.compops import events, scoreboard
from tournamentcontrol.competition.models import Match, MatchEvent
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_compops_results import DATASTAR
from tournamentcontrol.competition.tests.test_compops_scoreboard import (
    ScoreboardFixture,
    at,
)


@freeze_time("2026-10-08 19:05 +10:00")
class ScorerEventTests(ScoreboardFixture):
    """The 19:00 match on Field 1: halves of 15 minutes, started on time."""

    def test_add_records_a_score_with_who_and_when(self):
        self.press("scorer-score", side="home", step="up")
        event = self.first.events.get()
        self.assertEqual(
            (
                event.kind,
                event.side,
                event.points,
                event.recorded_by,
                event.recorded_at,
                event.period,
                event.remaining,
            ),
            ("score", "home", 1, self.scorer, at(19, 5), 1, 600),
        )

    def test_take_off_reverses_the_sides_latest_score(self):
        self.press("scorer-score", side="home", step="up")
        self.press("scorer-score", side="away", step="up")
        self.press("scorer-score", side="home", step="up")
        latest = self.first.events.filter(side="home").last()
        self.press("scorer-score", side="home", step="down")
        correction = self.first.events.get(kind=MatchEvent.Kind.CORRECTION)
        self.assertEqual(
            (correction.reverses, correction.recorded_by), (latest, self.scorer)
        )
        self.first.refresh_from_db()
        self.assertEqual(
            (
                self.first.home_team_progress_score,
                self.first.away_team_progress_score,
            ),
            (1, 1),
        )
        self.assertEqual(self.first.events.totals(), {"home": 1, "away": 1})

    def test_score_kept_before_the_log_is_still_taken_off(self):
        Match.objects.filter(pk=self.first.pk).update(home_team_progress_score=2)
        self.press("scorer-score", side="home", step="down")
        self.first.refresh_from_db()
        self.assertEqual(self.first.home_team_progress_score, 1)
        self.assertEqual(self.first.events.count(), 0)


@freeze_time("2026-10-08 19:05 +10:00")
class StartEventTests(ScoreboardFixture):
    """A venue whose clocks are started by hand."""

    def setUp(self):
        super().setUp()
        self.venue.scoreboard_auto_start = False
        self.venue.save()

    def test_scorer_starting_the_clock_records_a_start_once(self):
        self.press("scorer-start")
        with freeze_time("2026-10-08 19:06 +10:00"):
            self.press("scorer-start")
        event = self.first.events.get()
        self.assertEqual(
            (
                event.kind,
                event.side,
                event.recorded_by,
                event.recorded_at,
                event.period,
                event.remaining,
            ),
            ("start", "", self.scorer, at(19, 5), 1, 900),
        )

    def test_timekeeper_records_a_start_for_each_clock_it_starts(self):
        self.venue.slug = "the-park"
        self.venue.slug_locked = True
        self.venue.save()
        field2 = factories.GroundFactory.create(venue=self.venue, title="Field 2")
        other = self.match(19, self.fji, self.nzl, ground=field2)
        # A clock the ground's scorer started keeps its start, and its event.
        self.press("scorer-start")
        url = self.reverse(
            "compops:timekeeper-start",
            competition="pacific-cup",
            season="pc26",
            venue="the-park",
            kick_off=int(at(19).timestamp()),
        )
        with self.login(self.scorer), self.captureOnCommitCallbacks(execute=True):
            self.post(url)
            self.post(url)
        self.assertEqual(
            {
                match: list(match.events.values_list("kind", "recorded_by"))
                for match in (self.first, other, self.second)
            },
            {
                self.first: [("start", self.scorer.pk)],
                other: [("start", self.scorer.pk)],
                self.second: [],
            },
        )


@freeze_time("2026-10-08 19:05 +10:00")
class WhoScoredTests(ScoreboardFixture):
    """Australia has two players linked; New Zealand has none."""

    def setUp(self):
        super().setUp()
        self.seven = self.link(self.aus, 7, "Jo", "Bloggs")
        self.nine = self.link(self.aus, 9, "Sam", "Smith")
        self.coach = self.link(self.aus, None, "Pat", "Coach", is_player=False)
        self.kiwi = self.link(self.nzl, 4, "Kim", "Kiwi", is_player=False)

    def link(self, team, number, first_name, last_name, is_player=True):
        return factories.TeamAssociationFactory.create(
            team=team,
            number=number,
            is_player=is_player,
            person__first_name=first_name,
            person__last_name=last_name,
        ).person

    def player_url(self, event):
        return self.reverse(
            "compops:scorer-player",
            match_pk=self.first.pk,
            event_pk=event.pk,
            **self.kw,
        )

    def pick(self, event, person, user=None):
        with (
            self.login(user or self.scorer),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.post(
                self.player_url(event),
                data={"player": "" if person is None else person.pk},
                extra=DATASTAR,
            )

    def test_score_asks_who_scored_from_the_teams_players(self):
        body = self.press("scorer-score", side="home", step="up")
        event = self.first.events.get()
        self.assertIn(f'data: signals {{"pick":{event.pk}}}', body)
        url = self.player_url(event)
        # One form for each player, and one to leave the score unnamed.
        self.assertEqual(body.count(f'<form method="post" action="{url}"'), 3)
        for person in (self.seven, self.nine):
            self.assertIn(
                f'<input type="hidden" name="player" value="{person.pk}">', body
            )
        self.assertNotIn(f'name="player" value="{self.coach.pk}"', body)
        self.assertIn(
            f'<button class="sc-ask" type="button" data-ask-match="{self.first.pk}"',
            body,
        )

    def test_team_with_no_players_is_not_asked(self):
        body = self.press("scorer-score", side="away", step="up")
        self.assertNotIn("datastar-patch-signals", body)
        self.assertNotIn(f'name="player" value="{self.kiwi.pk}"', body)

    def test_scorer_who_turned_the_question_off_is_not_asked(self):
        body = self.press("scorer-score", side="home", step="up", data={"ask": "0"})
        self.assertNotIn("datastar-patch-signals", body)
        self.assertEqual(self.first.events.count(), 1)

    def test_no_question_on_a_page_where_neither_team_has_players(self):
        self.aus.people.update(is_player=False)
        body = self.press("scorer-score", side="home", step="up")
        self.assertNotIn("datastar-patch-signals", body)
        self.assertNotIn("data-ask-match", body)

    def test_picking_a_player_names_the_scorer_and_tells_the_boards(self):
        self.press("scorer-score", side="home", step="up")
        event = self.first.events.get()
        events.reset_backend()
        self.pick(event, self.nine)
        self.assert_http_200_ok()
        body = b"".join(self.last_response.streaming_content).decode()
        self.assertIn('data: signals {"pick":0}', body)
        self.assertIn('<span class="sc-who-name">9 Sam Smith</span>', body)
        event.refresh_from_db()
        self.assertEqual(event.player, self.nine)
        (published,) = events.get_backend().recent(
            events.channel(self.season.pk, scoreboard.SCOPE)
        )
        self.assertEqual(
            (published["type"], published["match"]),
            ("scoreboard-changed", self.first.pk),
        )

    def test_player_is_changed_or_cleared_while_the_score_is_the_sides_latest(self):
        self.press("scorer-score", side="home", step="up")
        first = self.first.events.get()
        self.pick(first, self.nine)
        self.pick(first, self.seven)
        first.refresh_from_db()
        self.assertEqual(first.player, self.seven)
        self.pick(first, None)
        first.refresh_from_db()
        self.assertEqual(first.player, None)
        # Once another score is the latest, the first is the admin's to change.
        self.press("scorer-score", side="home", step="up")
        self.pick(first, self.nine)
        self.assert_http_400_bad_request()
        # And a score taken back is no score to name.
        latest = self.first.events.last()
        self.press("scorer-score", side="home", step="down")
        self.pick(latest, self.nine)
        self.assert_http_400_bad_request()
        first.refresh_from_db()
        latest.refresh_from_db()
        self.assertEqual((first.player, latest.player), (None, None))

    def test_picking_refuses_someone_who_does_not_play_for_the_team(self):
        self.press("scorer-score", side="home", step="up")
        event = self.first.events.get()
        for person in (self.coach, self.kiwi):
            with self.subTest(person=person):
                self.pick(event, person)
                self.assert_http_400_bad_request()
        event.refresh_from_db()
        self.assertEqual(event.player, None)

    def test_picking_needs_a_login_and_the_right_to_score(self):
        event = self.first.record_event(MatchEvent.Kind.SCORE, "home")
        self.post(self.player_url(event), data={"player": self.nine.pk})
        self.assert_http_302_found()
        self.pick(event, self.nine, user=self.outsider)
        self.assert_http_403_forbidden()
        with self.login(self.scorer):
            self.get(self.player_url(event))
        self.assert_http_405_method_not_allowed()
        event.refresh_from_db()
        self.assertEqual(event.player, None)

    def test_event_of_another_match_is_not_found(self):
        event = self.second.record_event(MatchEvent.Kind.SCORE, "away")
        self.pick(event, self.nine)
        self.assert_http_404_not_found()

    def test_form_post_without_scripts_returns_to_the_scorers_page(self):
        event = self.first.record_event(MatchEvent.Kind.SCORE, "home")
        with self.login(self.scorer):
            self.post(self.player_url(event), data={"player": self.nine.pk})
        self.assert_http_302_found(url=self.reverse("compops:scorer", **self.kw))
        event.refresh_from_db()
        self.assertEqual(event.player, self.nine)
