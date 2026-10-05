"""
Tests for the revolutioniseSPORT provider.

revolutioniseSPORT has no API, so the provider scrapes the public draws
pages. The HTTP boundary is replaced with an in-memory ``requests.Session``
stand-in that serves pages captured from Central Coast Hockey Association
(``fixtures/revolutionise``; see ``capture.txt`` there for the URL of each),
so that nothing here depends on the live site.
"""

from datetime import date, time
from unittest import mock
from zoneinfo import ZoneInfo

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.forms import CompetitionForm, SeasonForm
from tournamentcontrol.competition.models import (
    Division,
    Ground,
    LadderSummary,
    Match,
    Team,
    Venue,
)
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.upstream import (
    CCHA_MENS_URL,
    CCHA_URL,
    FakeResponse,
    ccha_session,
)
from tournamentcontrol.competition.upstream import (
    PROVIDERS,
    UpstreamResponseError,
    UpstreamTransportError,
    UpstreamURLError,
    provider_for_identifier,
    provider_for_url,
)
from tournamentcontrol.competition.upstream.revolutionise import (
    LadderRow,
    RevolutioniseClient,
    RevolutioniseProvider,
    RevolutioniseURL,
    infer_ladder_template,
)
from tournamentcontrol.competition.upstream.sync import (
    FINALS_STAGE_TITLE,
    REGULAR_STAGE_TITLE,
    synchronise_season,
)

SYDNEY = ZoneInfo("Australia/Sydney")
MENS_DIV_1 = "revolutionise:25527/3741"
MENS_DIV_2 = "revolutionise:25527/11184"
MENS_DIV_3 = "revolutionise:25527/11183"
CRUSHERS = "revolutionise:405394"
GOSFORD = "revolutionise:405375"

# The CCHA Mens Competition had been played to its Grand Final when the
# pages were captured.
CAPTURED_AT = "2026-10-05 14:00:00+11:00"


class URLTests(TestCase):
    def test_organisation_urls(self):
        for url in (
            "https://www.revolutionise.com.au/ccha",
            "https://www.revolutionise.com.au/ccha/",
            "https://www.revolutionise.com.au/ccha/games",
            "https://revolutionise.com.au/ccha/pointscores",
        ):
            parsed = RevolutioniseURL(url)
            self.assertEqual(parsed.slug, "ccha", url)
            self.assertEqual(parsed.competition_id, None, url)
            self.assertEqual(parsed.canonical, CCHA_URL, url)
            self.assertEqual(parsed.season_url, CCHA_URL, url)

    def test_competition_and_grade_urls(self):
        for url in (
            "https://www.revolutionise.com.au/ccha/games/25527",
            "https://www.revolutionise.com.au/ccha/games/25527/3741",
            "https://www.revolutionise.com.au/ccha/games/25527/3741/round/4",
            "https://www.revolutionise.com.au/ccha/pointscore/25527/3741",
        ):
            parsed = RevolutioniseURL(url)
            self.assertEqual(parsed.competition_id, 25527, url)
            self.assertEqual(parsed.canonical, CCHA_URL, url)
            self.assertEqual(parsed.season_url, CCHA_MENS_URL, url)
        parsed = RevolutioniseURL(
            "https://www.revolutionise.com.au/ccha/games/25527/3741"
        )
        self.assertEqual(parsed.grade_id, 3741)
        self.assertEqual(
            parsed.round_url(25527, 3741, 2),
            "https://www.revolutionise.com.au/ccha/games/25527/3741/round/2",
        )
        self.assertEqual(
            parsed.team_ical_url(25527, 405386),
            "https://www.revolutionise.com.au/ccha/games/team/export/ical/25527/405386",
        )

    def test_invalid_urls(self):
        for url in (
            "https://tfa.mysideline.com.au/competitions/association/6338",
            "https://www.revolutionise.com.au/",
            "https://www.revolutionise.com.au/ccha/shop",
            "https://www.revolutionise.com.au/ccha/games/x",
            "www.revolutionise.com.au/ccha/games",
        ):
            with self.assertRaises(UpstreamURLError, msg=url):
                RevolutioniseURL(url)


class RegistryTests(TestCase):
    def test_provider_for_url(self):
        self.assertEqual(provider_for_url(CCHA_URL).key, "revolutionise")
        self.assertEqual(
            provider_for_url(
                "https://tfa.mysideline.com.au/competitions/association/6338"
            ).key,
            "mysideline",
        )
        with self.assertRaises(UpstreamURLError):
            provider_for_url("https://example.com/ccha/games")

    def test_identifiers(self):
        provider = RevolutioniseProvider()
        self.assertEqual(provider.identifier("25527/3741"), MENS_DIV_1)
        self.assertEqual(provider.remote_id(MENS_DIV_1), "25527/3741")
        self.assertIs(
            provider_for_identifier(MENS_DIV_1).__class__, RevolutioniseProvider
        )
        self.assertEqual(provider_for_identifier("mysideline:1").key, "mysideline")
        self.assertEqual(provider_for_identifier("other:1"), None)
        self.assertEqual(provider_for_identifier(None), None)
        self.assertEqual(
            sorted(p.key for p in PROVIDERS), ["mysideline", "revolutionise"]
        )

    def test_season_url_belongs_to_the_organisation(self):
        provider = RevolutioniseProvider()
        self.assertEqual(
            provider.parse_competition_url("https://www.revolutionise.com.au/ccha"),
            CCHA_URL,
        )
        self.assertEqual(
            provider.parse_season_url(
                "https://www.revolutionise.com.au/ccha/games/25527/3741", CCHA_URL
            ),
            CCHA_MENS_URL,
        )
        self.assertEqual(provider.parse_season_url(CCHA_URL, CCHA_URL), CCHA_URL)
        with self.assertRaises(UpstreamURLError):
            provider.parse_season_url(
                "https://www.revolutionise.com.au/other/games/1", CCHA_URL
            )


class ClientTests(TestCase):
    """Parsing of the captured pages."""

    def setUp(self):
        super().setUp()
        self.session = ccha_session()
        self.client = RevolutioniseClient(session=self.session)
        self.url = RevolutioniseURL(CCHA_MENS_URL)

    def test_index(self):
        grades = self.client.get_index(self.url)
        self.assertEqual(len(grades), 14)
        self.assertEqual(
            [(g.competition_id, g.grade_id, g.grade_name) for g in grades[3:6]],
            [
                (25527, 3741, "Mens Division 1"),
                (25527, 11184, "Mens Division 2"),
                (25527, 11183, "Mens Division 3"),
            ],
        )
        self.assertEqual(grades[3].competition_name, "CCHA Mens Competition")
        self.assertEqual(grades[6].grade_name, "Under 8's")
        self.assertEqual(
            {g.competition_name for g in grades},
            {
                "CCHA Womens Competition",
                "CCHA Mens Competition",
                "CCHA Junior Competition",
                "CCHA Indoor 2026",
            },
        )
        method, url, kwargs = self.session.calls[0]
        self.assertEqual(url, CCHA_URL)
        self.assertEqual(kwargs["timeout"], (5, 30))
        self.assertTrue(self.session.headers["User-Agent"].startswith("vitriolic"))

    def test_grade(self):
        detail = self.client.get_grade(self.url, 25527, 3741)
        self.assertEqual(detail.competition_name, "CCHA Mens Competition")
        self.assertEqual(detail.grade_name, "Mens Division 1")
        self.assertEqual(detail.has_ladder, True)
        self.assertEqual(len(detail.rounds), 23)
        self.assertEqual(
            [(r.number, r.name, r.is_final) for r in detail.rounds[-4:]],
            [
                (20, "Round 20", False),
                (21, "Semi Finals", True),
                (22, "Finals", True),
                (23, "Grand Finals", True),
            ],
        )

    def test_grade_without_ladder_or_draws(self):
        detail = self.client.get_grade(self.url, 25530, 3743)
        self.assertEqual(detail.has_ladder, False)
        self.assertGreater(len(detail.rounds), 0)
        detail = self.client.get_grade(self.url, 27752, 30223)
        self.assertEqual(detail.rounds, ())
        self.assertEqual(detail.has_ladder, True)

    def test_round(self):
        detail = self.client.get_round(self.url, 25527, 3741, 1)
        self.assertEqual(detail.dates, (date(2026, 3, 20), date(2026, 3, 21)))
        self.assertEqual(detail.byes, ())
        self.assertEqual(len(detail.fixtures), 2)
        first = detail.fixtures[0]
        self.assertEqual(first.game_id, 2433163)
        self.assertEqual((first.date, first.time), (date(2026, 3, 20), time(20, 0)))
        self.assertEqual(
            (first.venue_id, first.venue_name), (3007, "Central Coast Hockey Park")
        )
        self.assertEqual(first.field, "Elaine Johnston Pitch")
        self.assertEqual((first.home_team_id, first.home_team_name), (405386, "Erina"))
        self.assertEqual(
            (first.away_team_id, first.away_team_name), (405394, "Crushers")
        )
        self.assertEqual((first.home_score, first.away_score), (6, 1))
        self.assertEqual(first.forfeiting_team_id, None)

    def test_round_with_forfeit(self):
        detail = self.client.get_round(self.url, 25527, 3741, 8)
        forfeit = next(f for f in detail.fixtures if f.game_id == 2433178)
        self.assertEqual(forfeit.forfeiting_team_id, 405375)
        self.assertEqual((forfeit.home_score, forfeit.away_score), (5, 0))
        # A forfeit recorded without a score.
        detail = self.client.get_round(self.url, 25532, 3751, 10)
        forfeit = next(f for f in detail.fixtures if f.game_id == 2418122)
        self.assertEqual(forfeit.forfeiting_team_id, 404540)
        self.assertEqual((forfeit.home_score, forfeit.away_score), (None, None))

    def test_round_with_byes(self):
        detail = self.client.get_round(self.url, 25527, 11184, 1)
        self.assertEqual(detail.dates, (date(2026, 3, 21),))
        self.assertEqual(
            [(b.team_id, b.team_name) for b in detail.byes], [(405387, "Erina")]
        )

    def test_round_not_yet_played(self):
        detail = self.client.get_round(self.url, 27681, 30192, 1)
        self.assertGreater(len(detail.fixtures), 0)
        self.assertEqual({f.home_score for f in detail.fixtures}, {None})
        self.assertEqual(detail.fixtures[0].field, None)
        self.assertEqual(detail.fixtures[0].venue_name, "Hawkesbury Brewing Co")

    def test_round_with_twelve_hour_times(self):
        # Water Polo Australia shows kick-offs as "8:00AM"; CCHA as "20:00".
        url = RevolutioniseURL("https://www.revolutionise.com.au/wpal/games/27412")
        detail = self.client.get_round(url, 27412, 23748, 1)
        self.assertEqual(
            [(f.date, f.time) for f in detail.fixtures[:3]],
            [
                (date(2026, 9, 29), time(8, 0)),
                (date(2026, 9, 29), time(9, 15)),
                (date(2026, 9, 29), time(10, 30)),
            ],
        )
        self.assertEqual(detail.fixtures[0].venue_name, "MSAC")
        self.assertEqual(detail.fixtures[0].field, "Outdoor Scoreboard")
        venue = self.client.get_venue_detail(url, 2637646)
        # The map on this page is an address search without coordinates.
        self.assertEqual(venue.address, "30 Aughtie Drive, Albert Park VIC 3206")
        self.assertEqual((venue.latitude, venue.longitude), (None, None))

    def test_round_with_finalists_to_be_determined(self):
        url = RevolutioniseURL(
            "https://www.revolutionise.com.au/qutnetball/games/26857"
        )
        detail = self.client.get_round(url, 26857, 41355, 10)
        self.assertEqual(len(detail.fixtures), 3)
        tbd = detail.fixtures[0]
        self.assertEqual(tbd.game_id, 2608962)
        self.assertEqual((tbd.home_team_id, tbd.away_team_id), (None, None))
        self.assertEqual((tbd.home_score, tbd.away_score), (None, None))
        self.assertEqual(tbd.time, time(18, 0))
        self.assertEqual(tbd.field, "Court 25")

    def test_ladder_with_bonus_points(self):
        url = RevolutioniseURL("https://www.revolutionise.com.au/wpal/games/27412")
        rows = self.client.get_ladder(url, 27412, 23747)
        self.assertEqual(len(rows), 8)
        self.assertEqual(
            [(r.team_name, r.counts["bonus"], r.points) for r in rows[3:6]],
            [
                ("SOUTH AUSTRALIA W15", 1, 13),
                ("ACT W15", 0, 12),
                ("WESTERN AUSTRALIA W15", -1, 11),
            ],
        )
        template, notes = infer_ladder_template(rows)
        self.assertEqual((template.points_win, template.points_loss), (3, 0))
        self.assertEqual(notes, ["no draws yet; 1 point(s) assumed for a draw"])

    def test_ladder_with_forfeit_penalty(self):
        # QUT Netball: 3/2/1 with a point deducted for a forfeit, ranked by a
        # win ratio column the parser ignores.
        url = RevolutioniseURL(
            "https://www.revolutionise.com.au/qutnetball/games/26857"
        )
        rows = self.client.get_ladder(url, 26857, 41355)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[3].counts["forfeits"], 1)
        self.assertEqual(rows[3].points, 13)
        template, notes = infer_ladder_template(rows)
        self.assertEqual(notes, [])
        self.assertEqual(
            template.points_formula,
            "3*win + 2*draw + 1*loss + 3*forfeit_for + -1*forfeit_against",
        )

    def test_ladder(self):
        rows = self.client.get_ladder(self.url, 25527, 3741)
        self.assertEqual(
            [(r.team_id, r.team_name, r.points) for r in rows],
            [
                (405394, "Crushers", 41),
                (405386, "Erina", 38),
                (405368, "The Entrance", 33),
                (405375, "Gosford", 31),
            ],
        )
        self.assertEqual(
            rows[3].counts,
            {
                "played": 18,
                "wins": 6,
                "draws": 2,
                "losses": 9,
                "forfeits": 1,
                "for": 40,
                "against": 58,
                "diff": -18,
            },
        )

    def test_timezone_from_ical(self):
        self.assertEqual(
            self.client.get_timezone(self.url, 25527, 405386), "Australia/Sydney"
        )

    def test_venue_detail_from_game_page(self):
        detail = self.client.get_venue_detail(self.url, 2433163)
        self.assertEqual(detail.address, "Hockey Ave, Wyong NSW 2259")
        self.assertAlmostEqual(detail.latitude, -33.2712, places=3)
        self.assertAlmostEqual(detail.longitude, 151.4458, places=3)

    def test_http_error(self):
        with self.assertRaises(UpstreamTransportError):
            self.client.get_round(self.url, 25527, 3741, 99)

    def test_page_without_listing_is_an_error(self):
        self.session.handlers[CCHA_URL] = lambda m, u, k: FakeResponse(
            text="<html><body><main><p>Maintenance</p></main></body></html>",
            content_type="text/html",
        )
        with self.assertRaises(UpstreamResponseError):
            self.client.get_index(self.url)
        self.session.handlers[self.url.round_url(25527, 3741, 1)] = (
            lambda m, u, k: FakeResponse(
                text="<html><body><main><div class='box-shadow-lg'>"
                "<div class='card card-hover'>no links</div></div></main></body></html>",
                content_type="text/html",
            )
        )
        with self.assertRaises(UpstreamResponseError):
            self.client.get_round(self.url, 25527, 3741, 1)


class InferenceTests(TestCase):
    def row(self, team_id, points, **counts):
        return LadderRow(
            team_id=team_id, team_name=str(team_id), counts=counts, points=points
        )

    def test_hockey_ladder(self):
        template, notes = infer_ladder_template(
            [
                self.row(1, 41, wins=10, draws=3, losses=5, forfeits=0),
                self.row(2, 38, wins=8, draws=4, losses=6, forfeits=0),
                self.row(3, 33, wins=6, draws=3, losses=9, forfeits=0),
                self.row(4, 31, wins=6, draws=2, losses=9, forfeits=1),
            ]
        )
        self.assertEqual(notes, [])
        self.assertEqual(
            (template.points_win, template.points_draw, template.points_loss),
            (3, 2, 1),
        )
        self.assertEqual(template.points_forfeit_for, 3)
        self.assertEqual(template.points_forfeit_against, 0)
        self.assertEqual(template.points_bye, 0)
        self.assertEqual(
            template.points_formula, "3*win + 2*draw + 1*loss + 3*forfeit_for"
        )

    def test_nothing_played_yet(self):
        template, notes = infer_ladder_template(
            [
                self.row(1, 0, wins=0, draws=0, losses=0),
                self.row(2, 0, wins=0, losses=0),
            ]
        )
        self.assertEqual(template, None)
        self.assertEqual(infer_ladder_template([]), (None, []))

    def test_underdetermined(self):
        # One result: 3 could be a 3-point win or a 1-point win plus ...
        template, notes = infer_ladder_template(
            [self.row(1, 3, wins=1, losses=0), self.row(2, 1, wins=0, losses=1)]
        )
        self.assertEqual(template.points_win, 3)
        self.assertEqual(template.points_loss, 1)
        self.assertEqual(template.points_draw, 1)
        self.assertEqual(notes, ["no draws yet; 1 point(s) assumed for a draw"])
        template, notes = infer_ladder_template(
            [self.row(1, 4, wins=1, draws=1), self.row(2, 4, wins=1, draws=1)]
        )
        self.assertEqual(template, None)


class SyncTests(TestCase):
    def setUp(self):
        super().setUp()
        self.season = factories.SeasonFactory.create(
            title="2026",
            timezone=SYDNEY,
            competition__title="Central Coast Hockey",
            competition__upstream_url=CCHA_URL,
            upstream_url=CCHA_MENS_URL,
        )
        self.session = ccha_session()
        self.revolutionise = RevolutioniseClient(session=self.session)

    def sync(self, renames=None):
        if renames is not None:
            self.session = ccha_session(renames=renames)
            self.revolutionise = RevolutioniseClient(session=self.session)
        with freeze_time(CAPTURED_AT):
            return synchronise_season(self.season, self.revolutionise)

    def test_import(self):
        result = self.sync()
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.created["division"], 3)
        self.assertEqual(result.created["team"], 15)
        self.assertEqual(result.created["match"], 170)
        self.assertEqual(result.created["venue"], 1)
        self.assertEqual(result.created["ground"], 3)
        self.assertEqual(result.created["stage"], 6)
        self.assertEqual(result.updated, {})
        self.assertEqual(result.deleted, {})

        self.assertEqual(
            list(self.season.divisions.values_list("upstream_id", "title", "order")),
            [
                (MENS_DIV_1, "Mens Division 1", 1),
                (MENS_DIV_2, "Mens Division 2", 2),
                (MENS_DIV_3, "Mens Division 3", 3),
            ],
        )
        division = self.season.divisions.get(upstream_id=MENS_DIV_1)
        self.assertEqual(division.upstream_provider.name, "revolutioniseSPORT")
        self.assertEqual(division.upstream_title, "Mens Division 1")
        # The points scheme was inferred from the ladder, the forfeit score
        # from the forfeit that was played with one.
        self.assertEqual(
            division.points_formula, "3*win + 2*draw + 1*loss + 3*forfeit_for"
        )
        self.assertEqual(division.forfeit_for_score, 5)
        self.assertEqual(division.forfeit_against_score, 0)
        self.assertEqual(
            list(division.stages.values_list("title", "order", "keep_ladder")),
            [(REGULAR_STAGE_TITLE, 1, True), (FINALS_STAGE_TITLE, 2, False)],
        )
        self.assertEqual(
            list(division.teams.values_list("upstream_id", "title")),
            [
                (CRUSHERS, "Crushers"),
                ("revolutionise:405386", "Erina"),
                ("revolutionise:405368", "The Entrance"),
                (GOSFORD, "Gosford"),
            ],
        )
        self.assertEqual(division.stages.get(order=1).pools.count(), 0)

        # Requests: index, then per grade its page, 23 rounds and ladder,
        # plus one iCalendar feed and one game page for the competition.
        self.assertEqual(len(self.session.calls), 1 + 3 * 25 + 1 + 1)

    def test_matches(self):
        self.sync()
        played = Match.objects.get(upstream_id="revolutionise:2433163")
        self.assertEqual(played.stage.title, REGULAR_STAGE_TITLE)
        self.assertEqual(played.round, 1)
        self.assertEqual(played.label, None)
        self.assertEqual(played.home_team.title, "Erina")
        self.assertEqual(played.away_team.title, "Crushers")
        self.assertEqual((played.home_team_score, played.away_team_score), (6, 1))
        self.assertEqual(played.date, date(2026, 3, 20))
        self.assertEqual(played.time, time(20, 0))
        self.assertEqual(played.datetime.astimezone(SYDNEY).hour, 20)
        self.assertEqual(played.play_at.title, "Elaine Johnston Pitch")
        venue = played.play_at.ground.venue
        self.assertEqual(venue.title, "Central Coast Hockey Park")
        self.assertEqual(venue.timezone, SYDNEY)
        self.assertEqual(venue.latlng.split(",")[2], "15")
        self.assertAlmostEqual(float(venue.latlng.split(",")[0]), -33.2712, places=3)
        self.assertEqual(
            sorted(Ground.objects.values_list("title", flat=True)),
            [
                "Elaine Johnston Pitch",
                "Elaine Johnston Pitch (H1)",
                "Garry Denson Pitch",
            ],
        )

        # A forfeit takes the division's forfeit scores, whatever was shown.
        forfeit = Match.objects.get(upstream_id="revolutionise:2433178")
        self.assertEqual(forfeit.is_forfeit, True)
        self.assertEqual(forfeit.forfeit_winner.title, "The Entrance")
        self.assertEqual((forfeit.home_team_score, forfeit.away_team_score), (5, 0))

        # Byes have no page of their own; they are dated by their round and
        # count once it is over.
        bye = Match.objects.get(upstream_id="revolutionise:bye/11184/1/405387")
        self.assertEqual(bye.is_bye, True)
        self.assertEqual(bye.bye_processed, True)
        self.assertEqual(bye.home_team.title, "Erina")
        self.assertEqual(bye.away_team, None)
        self.assertEqual(bye.date, date(2026, 3, 21))
        self.assertEqual((bye.time, bye.datetime, bye.play_at), (None, None, None))
        self.assertEqual(Match.objects.filter(is_bye=True).count(), 19)

        # Finals carry the round names and sit in the finals stage.
        final = Match.objects.get(upstream_id="revolutionise:2638987")
        self.assertEqual(final.stage.title, FINALS_STAGE_TITLE)
        self.assertEqual(final.label, "Grand Finals")
        self.assertEqual(final.round, 23)
        self.assertEqual((final.home_team_score, final.away_team_score), (4, 3))
        # ... and a final yet to be scored has no result.
        unplayed = Match.objects.get(upstream_id="revolutionise:2638985")
        self.assertEqual(
            (unplayed.home_team_score, unplayed.away_team_score), (None, None)
        )

    def test_ladder_matches_the_site(self):
        self.sync()
        division = self.season.divisions.get(upstream_id=MENS_DIV_1)
        ladder = LadderSummary.objects.filter(stage__division=division).order_by(
            "-points", "-difference"
        )
        # The points and positions are the site's. The Entrance's win by
        # forfeit is a forfeit_for here rather than one of its wins, and
        # Gosford's forfeit is a forfeit_against rather than a loss; both
        # count as played, as they do on the site.
        self.assertEqual(
            [
                (
                    row.team.title,
                    row.played,
                    row.win,
                    row.draw,
                    row.loss,
                    row.forfeit_for,
                    row.forfeit_against,
                    int(row.points),
                )
                for row in ladder
            ],
            [
                ("Crushers", 18, 10, 3, 5, 0, 0, 41),
                ("Erina", 18, 8, 4, 6, 0, 0, 38),
                ("The Entrance", 18, 5, 3, 9, 1, 0, 33),
                ("Gosford", 18, 6, 2, 9, 0, 1, 31),
            ],
        )
        self.assertEqual(
            division.stages.get(title=FINALS_STAGE_TITLE).ladder_summary.count(), 0
        )

    def test_repeat_is_idempotent(self):
        self.sync()
        result = self.sync()
        self.assertEqual(result.created, {})
        self.assertEqual(result.updated, {})
        self.assertEqual(result.deleted, {})
        self.assertEqual(result.detached, {})
        self.assertEqual(result.warnings, [])
        self.assertEqual(Match.objects.count(), 170)

    def test_remote_rename_is_applied_or_reported(self):
        self.sync()
        division = self.season.divisions.get(upstream_id=MENS_DIV_1)
        team = Team.objects.get(upstream_id=CRUSHERS)
        team.title = "Toukley Crushers"
        team.save()

        result = self.sync(
            renames={
                "Mens Division 1": "Mens Premier League",
                "Crushers": "Wyong Crushers",
            }
        )
        division.refresh_from_db()
        team.refresh_from_db()
        self.assertEqual(
            (division.title, division.slug),
            ("Mens Premier League", "mens-premier-league"),
        )
        self.assertEqual(team.title, "Toukley Crushers")
        self.assertEqual(team.upstream_title, "Wyong Crushers")
        self.assertTrue(team.upstream_title_changed)
        # Every grade's Crushers was renamed; only the one with a local name
        # is reported.
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Wyong Crushers", result.warnings[0])
        self.assertIn(CRUSHERS, result.warnings[0])

    def test_whole_organisation_needs_every_grade(self):
        # The index lists competitions whose pages were not captured, so a
        # season covering the whole organisation cannot be fetched; nothing
        # is written when any page is missing.
        self.season.upstream_url = CCHA_URL
        self.season.save()
        with self.assertRaises(UpstreamTransportError):
            self.sync()
        self.assertEqual(Division.objects.count(), 0)

    def test_competition_must_be_listed(self):
        self.season.upstream_url = "https://www.revolutionise.com.au/ccha/games/99999"
        self.season.save()
        with self.assertRaises(UpstreamResponseError):
            self.sync()
        self.assertEqual(Division.objects.count(), 0)

    def test_connection_failure_changes_nothing(self):
        self.sync()
        self.session.exception = ConnectionError("boom")
        before = list(Match.objects.values_list("pk", "home_team_score"))
        with self.assertRaises(UpstreamTransportError):
            with mock.patch(
                "tournamentcontrol.competition.upstream.base.requests.RequestException",
                ConnectionError,
            ):
                self.sync()
        self.assertEqual(
            list(Match.objects.values_list("pk", "home_team_score")), before
        )

    def test_missing_ical_and_game_page_fall_back(self):
        # The auxiliary pages decorate the import; the season's time zone and
        # no coordinates are used when they cannot be read.
        for url in list(self.session.handlers):
            if "/export/ical/" in url or "/game/" in url:
                del self.session.handlers[url]
        result = self.sync()
        self.assertEqual(result.created["division"], 3)
        venue = Venue.objects.get()
        self.assertEqual(venue.timezone, SYDNEY)
        self.assertEqual(venue.latlng, "")
        played = Match.objects.get(upstream_id="revolutionise:2433163")
        self.assertEqual(played.time, time(20, 0))

    def test_default_points_without_a_ladder(self):
        # Drop the ladder link and the ladder page itself: the division is
        # created with the default formula and the administrator is told.
        grade_url = RevolutioniseURL(CCHA_MENS_URL).grade_url(25527, 3741)
        original = self.session.handlers[grade_url]

        def without_ladder(method, url, kwargs):
            response = original(method, url, kwargs)
            response.text = response.text.replace("pointscore/25527/3741", "nowhere")
            return response

        self.session.handlers[grade_url] = without_ladder
        result = self.sync()
        division = self.season.divisions.get(upstream_id=MENS_DIV_1)
        self.assertEqual(
            division.points_formula, "3*win + 2*draw + 1*loss + 3*bye + 3*forfeit_for"
        )
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("no ladder", result.warnings[0])
        self.assertIn(MENS_DIV_1, result.warnings[0])


class AdminTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.season = factories.SeasonFactory.create(
            competition__upstream_url=CCHA_URL, upstream_url=CCHA_MENS_URL
        )
        self.args = (self.season.competition_id, self.season.pk)

    def test_season_list_names_the_provider(self):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:edit",
                self.season.competition_id,
                test_query_count=60,
            )
            self.assertResponseContains(
                '<span class="hidden-xs hidden-sm">&nbsp;revolutioniseSPORT</span>'
            )

    @mock.patch("tournamentcontrol.competition.admin.synchronise_upstream_season")
    def test_sync_view(self, task):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:upstream-sync", *self.args
            )
            self.assertResponseContains("<h3>Synchronise with revolutioniseSPORT</h3>")
            self.assertResponseContains(
                '<a href="%s" target="_blank" rel="noopener">%s</a>'
                % (CCHA_MENS_URL, CCHA_MENS_URL)
            )
            self.post("admin:fixja:competition:season:upstream-sync", *self.args)
            self.response_302()
        task.delay.assert_called_once_with(self.season.pk)

    def test_competition_form_canonicalises(self):
        competition = self.season.competition
        data = {"title": competition.title, "slug": competition.slug, "enabled": True}
        for url in (
            "https://www.revolutionise.com.au/ccha",
            "https://www.revolutionise.com.au/ccha/pointscores",
            "https://www.revolutionise.com.au/ccha/games/25527/3741",
        ):
            form = CompetitionForm(
                data=dict(data, upstream_url=url),
                instance=competition,
                user=self.superuser,
            )
            self.assertEqual(form.errors.get("upstream_url"), None, url)
            self.assertEqual(form.cleaned_data["upstream_url"], CCHA_URL)
        form = CompetitionForm(
            data=dict(data, upstream_url="https://www.revolutionise.com.au/ccha/shop"),
            instance=competition,
            user=self.superuser,
        )
        self.assertEqual(len(form.errors["upstream_url"]), 1)

    def test_season_form_validation(self):
        data = {
            "title": self.season.title,
            "slug": self.season.slug,
            "mode": self.season.mode,
            "live_stream_privacy": "public",
            "upstream_url": "https://www.revolutionise.com.au/ccha/games/25527/3741/round/3",
        }
        form = SeasonForm(data=data, instance=self.season, user=self.superuser)
        self.assertEqual(form.errors, {})
        self.assertEqual(form.cleaned_data["upstream_url"], CCHA_MENS_URL)

        form = SeasonForm(
            data=dict(data, upstream_url=CCHA_URL),
            instance=self.season,
            user=self.superuser,
        )
        self.assertEqual(form.errors, {})
        self.assertEqual(form.cleaned_data["upstream_url"], CCHA_URL)

        for url in (
            "https://www.revolutionise.com.au/other/games/25527",
            "https://tfa.mysideline.com.au/competitions/association/6338?season=2026",
        ):
            form = SeasonForm(
                data=dict(data, upstream_url=url),
                instance=self.season,
                user=self.superuser,
            )
            self.assertEqual(len(form.errors["upstream_url"]), 1, url)


class MigrationTests(TransactionTestCase):
    """
    The MySideline link of existing data becomes the generic upstream link.
    """

    migrate_from = [("competition", "0064_mysideline_titles")]
    migrate_to = [("competition", "0066_remove_mysideline")]

    def test_mysideline_data_is_carried_over(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Competition = apps.get_model("competition", "Competition")
        Season = apps.get_model("competition", "Season")
        Division = apps.get_model("competition", "Division")
        Team = apps.get_model("competition", "Team")

        competition = Competition.objects.create(
            title="State Cup",
            slug="state-cup",
            order=1,
            mysideline_url="https://tfa.mysideline.com.au/competitions/association/299999",
        )
        season = Season.objects.create(
            competition=competition,
            title="2025",
            slug="2025",
            order=1,
            mysideline_season=2025,
            mysideline_season_tag=2,
        )
        unlinked = Season.objects.create(
            competition=competition, title="2024", slug="2024", order=2
        )
        division = Division.objects.create(
            season=season,
            title="Men's Open A",
            slug="mens-open-a",
            order=1,
            mysideline_id=65396575,
            mysideline_title="2025 SC Men's Open A",
            mysideline_title_synced="2025 SC Men's Open A",
            points_formula="3*win",
        )
        team = Team.objects.create(
            division=division,
            title="Doyalson",
            slug="doyalson",
            order=1,
            mysideline_id=65576405,
            mysideline_title="2025 SC Doyalson MOA",
            mysideline_title_synced="2025 SC Doyalson MOA",
        )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Competition = apps.get_model("competition", "Competition")
        Season = apps.get_model("competition", "Season")
        Division = apps.get_model("competition", "Division")
        Team = apps.get_model("competition", "Team")

        self.assertEqual(
            Competition.objects.get(pk=competition.pk).upstream_url,
            "https://tfa.mysideline.com.au/competitions/association/299999",
        )
        self.assertEqual(
            Season.objects.get(pk=season.pk).upstream_url,
            "https://tfa.mysideline.com.au/competitions/association/299999"
            "?season=2025&seasonTag=2",
        )
        self.assertEqual(Season.objects.get(pk=unlinked.pk).upstream_url, None)
        division = Division.objects.get(pk=division.pk)
        self.assertEqual(division.upstream_id, "mysideline:65396575")
        self.assertEqual(division.upstream_title, "2025 SC Men's Open A")
        self.assertEqual(division.upstream_title_synced, "2025 SC Men's Open A")
        team = Team.objects.get(pk=team.pk)
        self.assertEqual(team.upstream_id, "mysideline:65576405")
        self.assertEqual(team.upstream_title, "2025 SC Doyalson MOA")

        # Migrate everything else forward again so later tests see the
        # expected schema.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
