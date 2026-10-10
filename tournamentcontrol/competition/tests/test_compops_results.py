import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission
from django.db import connection
from django.db.models.signals import post_save
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.compops.permissions import (
    can_change_match,
    can_stream,
)
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.signals.custom import score_updated
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")


@freeze_time("2026-10-08 00:00 +10:00")
class ResultsFixture(TestCase):
    def setUp(self):
        events.reset_backend()
        self.staff = factories.UserFactory.create(is_staff=True)
        self.staff.user_permissions.add(Permission.objects.get(codename="change_match"))
        self.readonly = factories.UserFactory.create(is_staff=True)
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
        )
        self.stage = factories.StageFactory.create(division__season=self.season)
        self.kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "datestr": "20261008",
        }
        self.match = self.make(8)

    def make(self, hour, **kwargs):
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, hour), TZ)
        return factories.MatchFactory.create(
            stage=self.stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            **kwargs,
        )

    def url(self, name, **extra):
        return reverse(f"compops:{name}", kwargs={**self.kw, **extra})

    def post_score(self, match, home, away, user=None, datastar=False, **extra):
        data = {"home_team_score": home, "away_team_score": away, **extra}
        headers = {"Datastar-Request": "true"} if datastar else {}
        with self.login(user or self.staff):
            return self.client.post(
                self.url("match-result", match_pk=match.pk), data, headers=headers
            )


class SlotFragmentTests(ResultsFixture):
    def test_pending_row_renders_the_form_without_values(self):
        with self.login(self.staff):
            self.get("compops:slot", slot_key="0800", **self.kw)
        self.response_200()
        self.assertResponseContains(
            '<input type="number" name="home_team_score" class="sc" '
            f'data-preserve-attr="value" id="m{self.match.pk}_home_team_score">'
        )

    def test_pending_row_reads_home_score_v_score_away(self):
        with self.login(self.staff):
            self.get("compops:slot", slot_key="0800", **self.kw)
        body = self.last_response.content.decode()
        positions = [
            body.index(needle)
            for needle in (
                f'<span class="team home">{self.match.home_team.title}</span>',
                'name="home_team_score"',
                '<span class="vs">–</span>',
                'name="away_team_score"',
                f'<span class="team away">{self.match.away_team.title}</span>',
            )
        ]
        self.assertEqual(positions, sorted(positions))

    def test_cancel_link_restores_the_pending_form(self):
        with self.login(self.staff):
            self.get("compops:match-result", match_pk=self.match.pk, **self.kw)
        self.assertResponseContains(
            '<input type="number" name="home_team_score" class="sc" '
            f'data-preserve-attr="value" id="m{self.match.pk}_home_team_score">'
        )

    def test_entered_row_renders_score_and_edit_link(self):
        done = self.make(8, home_team_score=3, away_team_score=1)
        with self.login(self.staff):
            self.get("compops:slot", slot_key="0800", **self.kw)
        self.assertResponseContains('<span class="score">3 – 1</span>')
        url = self.url("match-result-edit", match_pk=done.pk)
        self.assertResponseContains(
            f'<a class="btn sm" href="{url}" '
            f"data-on:click__prevent=\"@get('{url}')\">Edit</a>"
        )

    def test_entered_row_shows_the_names_either_side_of_the_score(self):
        done = self.make(8, home_team_score=5, away_team_score=4)
        with self.login(self.staff):
            self.get("compops:slot", slot_key="0800", **self.kw)
        self.assertResponseContains(
            f'<span class="team home">{done.home_team.title}</span>'
        )
        self.assertResponseContains('<span class="score">5 – 4</span>')
        self.assertResponseContains(
            f'<span class="team away">{done.away_team.title}</span>'
        )

    def test_readonly_user_sees_no_form(self):
        with self.login(self.readonly):
            self.get("compops:slot", slot_key="0800", **self.kw)
        self.assertResponseContains('<span class="score muted">not entered</span>')

    def test_unknown_slot_is_404(self):
        with self.login(self.staff):
            self.get("compops:slot", slot_key="0900", **self.kw)
        self.response_404()


class SaveScoreTests(ResultsFixture):
    def test_plain_post_saves_and_redirects(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_score(self.match, 5, 4)
        self.assertRedirects(response, self.url("day"), fetch_redirect_response=False)
        self.match.refresh_from_db()
        self.assertEqual(
            (self.match.home_team_score, self.match.away_team_score), (5, 4)
        )
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["type"], "score-entered")
        self.assertEqual(event["match"], self.match.pk)
        self.assertFalse(event["adjusted"])
        self.assertEqual(event["actor"], self.staff.get_username())

    def test_score_is_saved_before_the_signal_is_sent(self):
        seen = []

        def receiver(sender, match, **kwargs):
            seen.append(Match.objects.get(pk=match.pk).home_team_score)

        score_updated.connect(receiver, weak=False, dispatch_uid="test-order")
        self.addCleanup(score_updated.disconnect, dispatch_uid="test-order")
        self.post_score(self.match, 5, 4)
        self.assertEqual(seen, [5])

    def test_score_post_saves_the_match_once(self):
        saves = []

        def receiver(sender, instance, **kwargs):
            saves.append(instance.pk)

        post_save.connect(receiver, sender=Match, weak=False, dispatch_uid="test-once")
        self.addCleanup(post_save.disconnect, sender=Match, dispatch_uid="test-once")
        self.post_score(self.match, 5, 4)
        self.assertEqual(saves, [self.match.pk])

    def test_datastar_post_returns_row_header_and_count_patches(self):
        response = self.post_score(self.match, 5, 4, datastar=True)
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertIn(f'data: elements <div id="match-{self.match.pk}"', body)
        self.assertIn('data: elements <div id="slot-0800-h"', body)
        self.assertNotIn('data: elements <div id="slot-0800" class="slot"', body)
        self.assertIn(
            'data: elements <span id="results-count" class="count zero">0</span>', body
        )
        self.assertIn('data: elements <ul id="activity"', body)

    def test_datastar_post_leaves_the_other_rows_of_the_slot_alone(self):
        pending = self.make(8)
        response = self.post_score(self.match, 5, 4, datastar=True)
        body = b"".join(response.streaming_content).decode()
        self.assertNotIn(f'id="match-{pending.pk}"', body)
        self.assertIn('<span class="when">1 of 2 entered</span>', body)

    def test_missing_away_score_re_renders_errors(self):
        response = self.post_score(self.match, 5, "", datastar=True)
        body = b"".join(response.streaming_content).decode()
        self.assertIn("Both scores are required.", body)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_team_score)

    def test_forfeit(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post_score(
                self.match,
                "",
                "",
                is_forfeit="on",
                forfeit_winner=self.match.home_team.pk,
            )
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_forfeit)
        self.assertEqual(self.match.forfeit_winner, self.match.home_team)
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["type"], "score-entered")
        self.assertEqual(
            event["summary"],
            f"Forfeit · {self.stage.division.title} · "
            f"{self.match.home_team.title} v {self.match.away_team.title} → "
            f"{self.match.home_team.title}",
        )

    def test_without_change_match_is_403(self):
        response = self.post_score(self.match, 5, 4, user=self.readonly)
        self.assertEqual(response.status_code, 403)

    def test_mysideline_match_is_refused(self):
        mirrored = self.make(9, mysideline_id=5)
        response = self.post_score(mirrored, 5, 4)
        self.assertEqual(response.status_code, 400)

    def test_unprogressed_match_is_refused(self):
        undecided = factories.UndecidedTeamFactory.create(stage=self.stage)
        pending = self.make(9, home_team=None, home_team_undecided=undecided)
        response = self.post_score(pending, 5, 4)
        self.assertEqual(response.status_code, 400)

    def test_match_from_another_day_is_404(self):
        when = timezone.make_aware(datetime.datetime(2026, 10, 9, 8), TZ)
        other = factories.MatchFactory.create(
            stage=self.stage, datetime=when, date=when.date(), time=when.time()
        )
        response = self.post_score(other, 5, 4)
        self.assertEqual(response.status_code, 404)


class EditScoreTests(ResultsFixture):
    def test_cancel_link_restores_the_entered_row(self):
        done = self.make(8, home_team_score=3, away_team_score=1)
        with self.login(self.staff):
            self.get("compops:match-result", match_pk=done.pk, **self.kw)
        self.assertResponseContains('<span class="score">3 – 1</span>')

    def test_edit_renders_form_with_values(self):
        done = self.make(8, home_team_score=3, away_team_score=1)
        with self.login(self.staff):
            self.get("compops:match-result-edit", match_pk=done.pk, **self.kw)
        self.assertResponseContains(
            '<input type="number" name="home_team_score" value="3" class="sc" '
            f'data-preserve-attr="value" id="m{done.pk}_home_team_score">'
        )

    def test_adjusting_publishes_adjusted_event(self):
        done = self.make(8, home_team_score=3, away_team_score=1)
        with self.captureOnCommitCallbacks(execute=True):
            self.post_score(done, 3, 2)
        (event,) = events.recent(self.season.pk)
        self.assertTrue(event["adjusted"])
        self.assertEqual(
            event["summary"],
            f"Score · {done.stage.division.title} · {done.home_team.title} "
            f"3–2 {done.away_team.title}",
        )


class ByeTests(ResultsFixture):
    def test_bye_row_processes(self):
        bye = factories.MatchFactory.create(
            stage=self.stage,
            date=datetime.date(2026, 10, 8),
            time=None,
            datetime=None,
            is_bye=True,
            away_team=None,
        )
        with self.login(self.staff):
            self.get("compops:slot", slot_key="byes", **self.kw)
        self.assertResponseContains(
            '<input type="checkbox" name="bye_processed" class="bye" '
            f'id="m{bye.pk}_bye_processed">'
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.post_score(bye, "", "", bye_processed="on")
        bye.refresh_from_db()
        self.assertTrue(bye.bye_processed)
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["type"], "bye-processed")


class PermissionOrderTests(ResultsFixture):
    def fresh(self, user):
        # A fresh instance has no permission cache; warming the global one
        # leaves any later query to the guardian object check.
        user = type(user).objects.get(pk=user.pk)
        user.has_perm("competition.change_match")
        return user

    def test_global_permission_needs_no_object_query(self):
        user = self.fresh(self.staff)
        with self.assertNumQueries(0):
            self.assertTrue(can_change_match(user, self.match))

    def test_object_permission_is_still_honoured(self):
        assign_perm("competition.change_match", self.readonly, self.match)
        user = self.fresh(self.readonly)
        with CaptureQueriesContext(connection) as queries:
            self.assertTrue(can_change_match(user, self.match))
        # Without the global permission, the object check goes to guardian.
        self.assertGreater(len(queries), 0)

    def test_global_stream_permission_needs_no_object_query(self):
        self.staff.user_permissions.add(
            Permission.objects.get(codename="stream_season")
        )
        user = self.fresh(self.staff)
        with self.assertNumQueries(0):
            self.assertTrue(can_stream(user, self.season))
