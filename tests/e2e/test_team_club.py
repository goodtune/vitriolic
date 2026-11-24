"""End-to-end test of giving a team that has no club a club of its own."""

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests import factories

TEAM = "admin:fixja:competition:season:division:team"


class TestTeamClub:
    """Adding a person to a team without a club gives the team a club first."""

    @pytest.fixture
    def team(self, db):
        competition = factories.CompetitionFactory.create(title="Coastal Midweek Touch")
        season = factories.SeasonFactory.create(
            competition=competition, title="Spring 2026"
        )
        division = factories.DivisionFactory.create(season=season, title="Men's")
        return factories.TeamFactory.create(
            division=division, title="Terrigal Tide", club=None
        )

    def test_team_without_a_club_is_given_one(
        self, authenticated_page: Page, live_server, team, screenshot_dir
    ):
        """
        Purpose: a person belongs to a club and a team's people come from its
        club, so a team entered without one (a social competition) cannot
        have people. The admin offers to give the team a club named after it.

        Prerequisites: a competition with no clubs, and a team in it that has
        no club.

        Expected behaviour: the page that adds a person to the team leads to
        a page explaining why there is nobody to add, which says a club
        named after the team will be created. Accepting creates the club,
        adds it to the competition's clubs, gives it to the team and lands
        on the club, where its people are added.

        Limitations: the club is empty, so its people are still added by
        hand (or through the administration MCP tools) before they can be
        linked to the team.
        """
        page = authenticated_page
        division = team.division
        args = (
            division.season.competition_id,
            division.season_id,
            division.pk,
            team.pk,
        )

        page.goto(
            f"{live_server.url}{reverse(f'{TEAM}:teamassociation:add', args=args)}"
        )

        expect(page).to_have_url(
            f"{live_server.url}{reverse(f'{TEAM}:club', args=args)}"
        )
        expect(
            page.get_by_text(
                "A club named Terrigal Tide will be created, added to the clubs "
                "of Coastal Midweek Touch and given this team."
            )
        ).to_be_visible()
        page.screenshot(path=str(screenshot_dir / "team_club_page.png"))

        page.get_by_role("button", name="Give the team a club").first.click()

        # The message is on the page the club's creation redirects to, so
        # the club exists by the time it shows.
        expect(
            page.get_by_text(
                "Terrigal Tide is now in the club Terrigal Tide. Add its people "
                "to the club, then link them to the team."
            )
        ).to_be_visible()
        team.refresh_from_db()
        assert team.club.title == "Terrigal Tide"
        expect(page).to_have_url(f"{live_server.url}{team.club.urls['edit']}")
        page.screenshot(path=str(screenshot_dir / "team_club_created.png"))
        assert list(division.season.competition.clubs.all()) == [team.club]
