"""End-to-end check of the date column on a team's public schedule."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils.formats import date_format
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests import factories

UTC = ZoneInfo("UTC")

# Three games on the first day, two on the second, and a semi-final nobody has
# scheduled yet.
FIXTURES = (
    ("Ireland", datetime(2026, 7, 22, 9, 25, tzinfo=UTC), "Field 1", 8, 7),
    ("Wales", datetime(2026, 7, 22, 12, 10, tzinfo=UTC), "Field 3", 11, 7),
    ("England", datetime(2026, 7, 22, 16, 45, tzinfo=UTC), "Field 1", 3, 15),
    ("France", datetime(2026, 7, 23, 12, 10, tzinfo=UTC), "Field 2", 7, 5),
    ("Italy", datetime(2026, 7, 23, 15, 30, tzinfo=UTC), "Field 1", 9, 4),
)


class TestTeamSchedule:
    """The date heads the first game of each day and never repeats."""

    @pytest.fixture
    def team(self, db, settings):
        # The public competition site is placed dynamically by the content
        # app, so point at the urlconf that mounts it directly.
        settings.ROOT_URLCONF = "tournamentcontrol.competition.tests.urls"
        competition = factories.CompetitionFactory.create(title="World Cup")
        season = factories.SeasonFactory.create(
            competition=competition, title="2026", timezone="UTC"
        )
        division = factories.DivisionFactory.create(season=season, title="Men's Open")
        stage = factories.StageFactory.create(division=division, title="Pool A")
        team = factories.TeamFactory.create(
            division=division, title="Australia", club__title="Australia"
        )
        venue = factories.VenueFactory.create(season=season, title="Nottingham")
        grounds = {
            title: factories.GroundFactory.create(venue=venue, title=title)
            for title in ("Field 1", "Field 2", "Field 3")
        }
        for index, (title, when, ground, us, them) in enumerate(FIXTURES, start=1):
            factories.MatchFactory.create(
                stage=stage,
                round=index,
                home_team=team,
                away_team=factories.TeamFactory.create(
                    division=division, title=title, club__title=title
                ),
                datetime=when,
                play_at=grounds[ground],
                home_team_score=us,
                away_team_score=them,
            )
        factories.MatchFactory.create(
            stage=stage,
            round=len(FIXTURES) + 1,
            home_team=team,
            away_team=factories.TeamFactory.create(
                division=division, title="Samoa", club__title="Samoa"
            ),
            datetime=None,
            date=None,
            time=None,
            play_at=None,
        )
        return team

    def test_the_date_heads_the_first_game_of_each_day(
        self, page: Page, live_server, team, screenshot_dir
    ):
        """
        Purpose: the schedule is read on a phone more often than a desktop,
        and a date repeated down every row made a day with three games look
        no different to three days with one.

        Prerequisites: a team with three games on one day, two on the next,
        and one that has not been scheduled at all.

        Expected behaviour: the date is written against the first game of a
        day and left out of the rest, and the unscheduled group -- which
        ``Team.matches_by_date`` keys under no date at all -- is headed TBA
        rather than the literal ``None``.
        """
        url = reverse(
            "competition:team",
            args=[
                team.division.season.competition.slug,
                team.division.season.slug,
                team.division.slug,
                team.slug,
            ],
        )
        page.set_viewport_size({"width": 760, "height": 900})
        page.goto(f"{live_server.url}{url}")

        table = page.locator("table.team.draw")
        expect(table).to_be_visible()
        table.screenshot(path=str(screenshot_dir / "team_schedule_dates.png"))

        expect(table.locator("tbody td.date")).to_have_text(
            [
                date_format(date(2026, 7, 22)),
                "",
                "",
                date_format(date(2026, 7, 23)),
                "",
                "TBA",
            ]
        )
