"""
End-to-end validation of the public venue and ground match listings: a
spectator finds a venue from the season page, sees every match played there
grouped by day, narrows the listing to a single day, and drills into one
ground (field) of the venue.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Page, expect

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from tournamentcontrol.competition.tests.factories import (
    CompetitionFactory,
    DivisionFactory,
    GroundFactory,
    MatchFactory,
    SeasonFactory,
    StageFactory,
    TeamFactory,
    VenueFactory,
)

SYDNEY = ZoneInfo("Australia/Sydney")
BOTH_DAYS = ["Saturday, 15th June 2024", "Sunday, 16th June 2024"]


def _match(stage, home, away, play_at, day, hour):
    """
    Schedule a match at ``hour`` o'clock Sydney time on ``day``; the
    ``datetime`` must be given explicitly or MatchFactory randomises it.
    """
    local = datetime.combine(day, time(hour, 0), tzinfo=SYDNEY)
    return MatchFactory.create(
        stage=stage,
        home_team=home,
        away_team=away,
        play_at=play_at,
        date=day,
        time=local.time(),
        datetime=local,
    )


@pytest.fixture
def venue_dataset(db):
    """
    Publish the competition application at ``/competitions/`` with one
    season played across two fields of a venue over two days.
    """
    placeholder, _ = Placeholder.objects.get_or_create(
        path="tournamentcontrol.competition.sites.CompetitionSite",
        namespace="competition",
    )
    SitemapNode.objects.create(
        title="Competitions", slug="competitions", object=placeholder
    )

    competition = CompetitionFactory.create(title="Touch Cup", slug="touch-cup")
    season = SeasonFactory.create(
        competition=competition, title="2024", slug="2024", timezone=SYDNEY
    )
    venue = VenueFactory.create(
        season=season, title="Bill Hartley Fields", slug="bill-hartley-fields"
    )
    field_1 = GroundFactory.create(venue=venue, title="Field 1", slug="field-1")
    field_2 = GroundFactory.create(venue=venue, title="Field 2", slug="field-2")

    # a second venue, whose matches must never leak into the first
    other_venue = VenueFactory.create(
        season=season, title="Elsewhere Park", slug="elsewhere-park"
    )

    division = DivisionFactory.create(
        season=season, title="Mixed Open", slug="mixed-open"
    )
    stage = StageFactory.create(division=division, title="Round Robin")
    sharks, eels, tigers, dragons = (
        TeamFactory.create(division=division, title=title)
        for title in ("Sharks", "Eels", "Tigers", "Dragons")
    )

    saturday = date(2024, 6, 15)
    sunday = date(2024, 6, 16)
    _match(stage, sharks, eels, field_1, saturday, 9)
    _match(stage, tigers, dragons, field_2, saturday, 10)
    _match(stage, sharks, tigers, field_2, sunday, 9)
    _match(stage, eels, dragons, other_venue, sunday, 11)

    return season


class TestVenueMatches:
    def test_browse_venue_and_ground(
        self, page: Page, live_server, venue_dataset, screenshot_dir
    ):
        """
        Browse from the season page to a venue, a single day at the venue,
        and a single ground.

        Prerequisites:
        - The competition application is published at /competitions/
        - A season with two venues; the first has two fields and hosts
          matches across two days

        Expected behaviour:
        - The season page links to each of its venues
        - The venue page links to each of its fields and to each day with
          matches, and lists every match on any of its fields, by day,
          with the field it is played on and its local kick-off time
        - Choosing a day narrows the listing to that day's matches
        - Choosing a field narrows the listing to that field's matches and
          links back to the venue
        - Matches at another venue never appear

        Screenshots of each page are saved as evidence.
        """
        season = venue_dataset
        base = (
            f"{live_server.url}/competitions/{season.competition.slug}/{season.slug}"
        )

        # Season: the venues are listed and linked.
        page.goto(f"{base}/")
        venues = page.locator("#venues")
        expect(venues.get_by_role("link", name="Bill Hartley Fields")).to_be_visible()
        expect(venues.get_by_role("link", name="Elsewhere Park")).to_be_visible()
        page.screenshot(path=screenshot_dir / "venue_season.png", full_page=True)

        # Venue: every match on either field, grouped by day.
        venues.get_by_role("link", name="Bill Hartley Fields").click()
        page.wait_for_url(f"{base}/venue/bill-hartley-fields/")
        expect(page.locator("h2")).to_have_text("Bill Hartley Fields")
        grounds = page.locator("#grounds")
        expect(grounds.get_by_role("link", name="Field 1")).to_be_visible()
        expect(grounds.get_by_role("link", name="Field 2")).to_be_visible()

        days = page.locator("h3.date")
        expect(days).to_have_text(BOTH_DAYS)
        rows = page.locator("table.place-matches tbody tr")
        expect(rows).to_have_count(3)
        # kick-off times are shown in the venue's local time
        expect(rows.nth(0).locator("td.time")).to_have_text("9 a.m.")
        expect(rows.nth(0).locator("td.ground")).to_have_text("Field 1")
        expect(rows.nth(0).locator("td.team.home")).to_have_text("Sharks")
        expect(rows.nth(1).locator("td.ground")).to_have_text("Field 2")
        expect(rows.nth(1).locator("td.team.home")).to_have_text("Tigers")
        expect(rows.nth(2).locator("td.team.away")).to_have_text("Tigers")
        expect(page.get_by_text("Dragons")).to_have_count(1)
        page.screenshot(path=screenshot_dir / "venue_all_days.png", full_page=True)

        # Venue, single day: only Sunday's match at this venue.
        page.locator("#dates").get_by_role("link", name="Sun 16 Jun").click()
        page.wait_for_url(f"{base}/venue/bill-hartley-fields/20240616/")
        expect(page.locator("#dates li.current")).to_have_text("Sun 16 Jun")
        expect(days).to_have_text(["Sunday, 16th June 2024"])
        expect(rows).to_have_count(1)
        expect(rows.first.locator("td.team.home")).to_have_text("Sharks")
        expect(rows.first.locator("td.team.away")).to_have_text("Tigers")
        page.screenshot(path=screenshot_dir / "venue_single_day.png", full_page=True)

        # Back to every day, then into a single field.
        page.locator("#dates").get_by_role("link", name="All days").click()
        page.wait_for_url(f"{base}/venue/bill-hartley-fields/")
        page.locator("#grounds").get_by_role("link", name="Field 2").click()
        page.wait_for_url(f"{base}/venue/bill-hartley-fields/ground/field-2/")
        expect(page.locator("h2")).to_have_text("Bill Hartley Fields - Field 2")
        expect(days).to_have_text(BOTH_DAYS)
        expect(rows).to_have_count(2)
        expect(rows.nth(0).locator("td.team.home")).to_have_text("Tigers")
        expect(rows.nth(1).locator("td.team.home")).to_have_text("Sharks")
        # the field column is redundant on a single ground
        expect(page.locator("td.ground")).to_have_count(0)
        page.screenshot(path=screenshot_dir / "ground_all_days.png", full_page=True)

        # Each match links through to its detail page.
        expect(rows.first.get_by_role("link", name="Detail")).to_have_attribute(
            "href",
            f"/competitions/touch-cup/2024/mixed-open/match:"
            f"{season.matches.get(home_team__title='Tigers').pk}/",
        )

        # The heading links back to the venue.
        page.locator("h2").get_by_role("link", name="Bill Hartley Fields").click()
        page.wait_for_url(f"{base}/venue/bill-hartley-fields/")

    def test_unknown_day_is_not_found(self, page: Page, live_server, venue_dataset):
        """
        A day on which the venue hosts no matches is not a valid listing.

        Expected behaviour:
        - /venue/<venue>/<day>/ for a day without matches returns 404
        - /venue/<venue>/<day>/ for a malformed day returns 404
        """
        season = venue_dataset
        base = (
            f"{live_server.url}/competitions/{season.competition.slug}/{season.slug}"
        )
        response = page.goto(f"{base}/venue/bill-hartley-fields/20240617/")
        assert response.status == 404
        response = page.goto(f"{base}/venue/bill-hartley-fields/20241399/")
        assert response.status == 404
