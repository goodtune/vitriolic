"""
End-to-end validation that a competition imported from MySideline renders
on the public site.

The NSW State Cup 2025 (MySideline association 299999) is imported from
captured responses -- a complete tournament of 21 divisions, pools and
finals -- and the season, division, pool and finals pages are exercised in
the browser with screenshots captured as evidence.

Set ``MYSIDELINE_LIVE=1`` to import from the live site instead of the
captured responses (read-only; useful to confirm the remote interface
still behaves as documented in ``docs/mysideline.md``).
"""

import os
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Page, expect

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from tournamentcontrol.competition.models import Competition, Season
from tournamentcontrol.competition.mysideline.client import MySidelineClient
from tournamentcontrol.competition.mysideline.sync import synchronise_season
from tournamentcontrol.competition.tests.mysideline import (
    STATE_CUP_SEASON,
    STATE_CUP_URL,
    state_cup_session,
)

MENS_OPEN_A = 65396575


@pytest.fixture
def state_cup(db):
    """
    Publish the competition application at ``/competitions/`` and import
    the NSW State Cup 2025 into it.
    """
    placeholder, _ = Placeholder.objects.get_or_create(
        path="tournamentcontrol.competition.sites.CompetitionSite",
        namespace="competition",
    )
    SitemapNode.objects.create(
        title="Competitions", slug="competitions", object=placeholder
    )
    competition = Competition.objects.create(
        title="NSW State Cup",
        slug="nsw-state-cup",
        order=1,
        mysideline_url=STATE_CUP_URL,
    )
    season = Season.objects.create(
        competition=competition,
        title=str(STATE_CUP_SEASON),
        slug=str(STATE_CUP_SEASON),
        order=1,
        timezone=ZoneInfo("Australia/Sydney"),
        mysideline_season=STATE_CUP_SEASON,
    )
    if os.environ.get("MYSIDELINE_LIVE"):
        client = MySidelineClient()
    else:
        client = MySidelineClient(session=state_cup_session())
    result = synchronise_season(season, client)
    assert result.warnings == []
    assert result.created["division"] >= 1
    return season


class TestMySidelineImportRenders:
    def test_state_cup_pages(self, page: Page, live_server, state_cup, screenshot_dir):
        """
        Browse a MySideline-imported season on the public site.

        Prerequisites:
        - The competition application is published at /competitions/
        - The NSW State Cup 2025 has been imported from MySideline

        Expected behaviour:
        - The season page lists every imported division
        - A division page shows its pools, the teams in them and the results
        - A pool page shows the ladder in the same order as MySideline
        - The finals page shows the finals fixtures by their MySideline names

        Screenshots of each page are saved as evidence.
        """
        season = state_cup
        division = season.divisions.get(mysideline_id=MENS_OPEN_A)
        base = f"{live_server.url}/competitions/{season.competition.slug}/{season.slug}"

        # Season: every division is listed.
        page.goto(f"{base}/")
        for title in season.divisions.values_list("title", flat=True):
            expect(page.get_by_role("link", name=title)).to_be_visible()
        page.screenshot(path=screenshot_dir / "mysideline_season.png", full_page=True)

        # Division: pools, teams and results.
        page.goto(f"{base}/{division.slug}/")
        expect(page.get_by_text(division.title).first).to_be_visible()
        for pool in ("Pool A", "Pool B"):
            expect(page.get_by_text(pool).first).to_be_visible()
        expect(page.get_by_text("2025 SC Doyalson MOA").first).to_be_visible()
        page.screenshot(path=screenshot_dir / "mysideline_division.png", full_page=True)

        # Pool: the ladder matches MySideline's ordering for Pool A.
        page.goto(f"{base}/{division.slug}:regular-season:pool-a/")
        rows = page.locator("table.ladder tbody tr, table tbody tr").filter(
            has_text="MOA"
        )
        expect(rows.first).to_be_visible()
        names = [
            row.locator("td").first.inner_text().strip()
            for row in rows.all()
            if "MOA" in row.inner_text()
        ]
        assert names[:2] == ["2025 SC Doyalson MOA", "2025 SC Parramatta MOA"]
        page.screenshot(path=screenshot_dir / "mysideline_pool.png", full_page=True)

        # Finals: fixtures carry the MySideline round names and, being an
        # elimination series, there is no ladder.
        page.goto(f"{base}/{division.slug}:finals/")
        expect(page.get_by_text("Grand Final").first).to_be_visible()
        expect(page.get_by_text("Quarter Final 1").first).to_be_visible()
        expect(page.locator("table.ladder")).to_have_count(0)
        page.screenshot(path=screenshot_dir / "mysideline_finals.png", full_page=True)
