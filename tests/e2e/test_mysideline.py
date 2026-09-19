"""
End-to-end validation that a competition imported from MySideline renders
on the public site, and that the admin lets an administrator publish a
different name from the one MySideline uses.

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
from django.urls import reverse
from playwright.sync_api import Page, expect

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from tournamentcontrol.competition.models import Competition, Season, Team
from tournamentcontrol.competition.mysideline.client import MySidelineClient
from tournamentcontrol.competition.mysideline.sync import synchronise_season
from tournamentcontrol.competition.tests.mysideline import (
    STATE_CUP_SEASON,
    STATE_CUP_URL,
    state_cup_session,
)

MENS_OPEN_A = 65396575
DOYALSON = 65576405

# What MySideline publishes for them, and what a Vitriolic administrator
# would rather see on the site: the season prefix and the grade suffix are
# noise once you are already looking at the 2025 season.
REMOTE_DIVISION = "2025 SC Men's Open A"
LOCAL_DIVISION = "Men's Open A"
REMOTE_TEAM = "2025 SC Doyalson MOA"
LOCAL_TEAM = "Doyalson"

# ... and what MySideline renames them to afterwards, which nobody here
# asked for and which must not quietly overwrite the names above.
RENAMED_DIVISION = "2025 SC Men's Open A Grade"
RENAMED_TEAM = "2025 SC Doyalson Men's Open A"
RENAMES = {REMOTE_DIVISION: RENAMED_DIVISION, REMOTE_TEAM: RENAMED_TEAM}


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


@pytest.mark.skipif(
    bool(os.environ.get("MYSIDELINE_LIVE")),
    reason="plays back an upstream rename, which the live site will not do on cue",
)
class TestMySidelineNameDeviations:
    """
    MySideline is authoritative for the draw and results but not for
    names: an administrator may publish something better than the remote
    name, and MySideline renaming the record afterwards must be reported
    rather than quietly applied or quietly discarded.
    """

    def _resync(self, season, renames=None):
        client = MySidelineClient(session=state_cup_session(renames=renames))
        return synchronise_season(season, client)

    def test_local_name_survives_resync_and_can_be_given_back(
        self, authenticated_page: Page, live_server, state_cup, screenshot_dir
    ):
        """
        Walk an administrator through publishing their own names and then
        dealing with an upstream rename of the same records.

        Prerequisites:
        - The NSW State Cup 2025 has been imported from MySideline
        - An authenticated administrator

        Expected behaviour:
        - Editing the title of a linked division or team is enough to keep
          that name; the next synchronisation does not overwrite it
        - The edit form states what MySideline calls the record, and offers
          "Use the MySideline name" to hand the name back
        - After MySideline renames such a record the synchronisation
          reports it, the season's MySideline page lists the records
          awaiting a decision, and the edit form names both the old and the
          new remote name
        - Accepting the remote name restores it (and the slug); saving
          without accepting keeps the local name and stops the report

        Screenshots of each admin page are saved as evidence.
        """
        page = authenticated_page
        season = state_cup
        division = season.divisions.get(mysideline_id=MENS_OPEN_A)
        team = Team.objects.get(mysideline_id=DOYALSON)
        assert (division.title, team.title) == (REMOTE_DIVISION, REMOTE_TEAM)

        sync_url = live_server.url + reverse(
            "admin:fixja:competition:season:mysideline-sync",
            args=[season.competition_id, season.pk],
        )
        division_url = f"{live_server.url}{division.urls['edit']}"
        team_url = f"{live_server.url}{team.urls['edit']}"

        # Publish our own names, simply by editing the records.
        for url, name in ((division_url, LOCAL_DIVISION), (team_url, LOCAL_TEAM)):
            self._save(page, url, title=name)
        division.refresh_from_db()
        team.refresh_from_db()
        assert (division.title, team.title) == (LOCAL_DIVISION, LOCAL_TEAM)
        assert (division.slug, team.slug) == ("mens-open-a", "doyalson")
        # The remote names are still recorded, ours is only a variation.
        assert division.mysideline_title == REMOTE_DIVISION
        assert division.mysideline_title_overridden
        assert not division.mysideline_title_changed

        # The form says what MySideline calls it, and offers to hand the
        # name back.
        page.goto(division_url)
        expect(self._help(page, "MySideline calls this")).to_have_text(
            "MySideline calls this “%s”." % REMOTE_DIVISION
        )
        expect(page.locator('input[name="mysideline_title_reset"]')).to_be_visible()
        page.screenshot(
            path=str(screenshot_dir / "mysideline_admin_division_local_name.png"),
            full_page=True,
        )

        # Synchronising again leaves our names alone, and reports nothing
        # because MySideline has not changed its own.
        result = self._resync(season)
        assert result.warnings == []
        division.refresh_from_db()
        team.refresh_from_db()
        assert (division.title, team.title) == (LOCAL_DIVISION, LOCAL_TEAM)

        # Now MySideline renames both records. Neither is overwritten, and
        # both are reported.
        result = self._resync(season, RENAMES)
        assert len(result.warnings) == 2, result.warnings
        assert any(RENAMED_DIVISION in warning for warning in result.warnings)
        assert any(RENAMED_TEAM in warning for warning in result.warnings)
        division.refresh_from_db()
        team.refresh_from_db()
        assert (division.title, team.title) == (LOCAL_DIVISION, LOCAL_TEAM)
        assert division.mysideline_title == RENAMED_DIVISION
        assert division.mysideline_title_changed

        # The season's MySideline page lists what is waiting on a decision.
        page.goto(sync_url)
        alert = page.locator(".mysideline-renamed")
        expect(
            alert.get_by_role("link", name=LOCAL_DIVISION, exact=True)
        ).to_be_visible()
        expect(alert.get_by_role("link", name=LOCAL_TEAM, exact=True)).to_be_visible()
        expect(alert).to_contain_text(RENAMED_DIVISION)
        expect(alert).to_contain_text(RENAMED_TEAM)
        page.screenshot(
            path=str(screenshot_dir / "mysideline_admin_sync_deviations.png"),
            full_page=True,
        )

        # Each edit form names the old and the new remote name.
        page.goto(division_url)
        expect(self._help(page, "MySideline has renamed this")).to_have_text(
            "MySideline has renamed this from “%s” to “%s”."
            % (REMOTE_DIVISION, RENAMED_DIVISION)
        )
        page.screenshot(
            path=str(screenshot_dir / "mysideline_admin_division_renamed.png"),
            full_page=True,
        )
        page.goto(team_url)
        expect(self._help(page, "MySideline has renamed this")).to_have_text(
            "MySideline has renamed this from “%s” to “%s”."
            % (REMOTE_TEAM, RENAMED_TEAM)
        )
        page.screenshot(
            path=str(screenshot_dir / "mysideline_admin_team_renamed.png"),
            full_page=True,
        )

        # Hand the division's name back to MySideline, and keep ours for
        # the team by saving it as it stands.
        self._save(page, division_url, mysideline_title_reset=True)
        self._save(page, team_url)
        division.refresh_from_db()
        team.refresh_from_db()
        assert division.title == RENAMED_DIVISION
        assert division.slug == "2025-sc-mens-open-a-grade"
        assert not division.mysideline_title_overridden
        assert team.title == LOCAL_TEAM
        assert team.mysideline_title_overridden
        assert not team.mysideline_title_changed

        # Nothing is waiting on a decision any more ...
        page.goto(sync_url)
        expect(page.locator(".mysideline-renamed")).to_have_count(0)
        page.screenshot(
            path=str(screenshot_dir / "mysideline_admin_sync_resolved.png"),
            full_page=True,
        )

        # ... and the next synchronisation is quiet: the division follows
        # MySideline again, the team keeps the name we chose.
        result = self._resync(season, RENAMES)
        assert result.warnings == []
        division.refresh_from_db()
        team.refresh_from_db()
        assert (division.title, team.title) == (RENAMED_DIVISION, LOCAL_TEAM)

    def _help(self, page: Page, starts_with):
        """The form help text which begins with ``starts_with``."""
        return page.locator("p.help-block", has_text=starts_with).first

    def _save(self, page: Page, url, title=None, mysideline_title_reset=False):
        """Open an admin edit form, optionally change it, and save it."""
        page.goto(url)
        if title is not None:
            page.fill('input[name="title"]', title)
        if mysideline_title_reset:
            page.check('input[name="mysideline_title_reset"]')
        # Wait for the POST itself, not just for a page to be loaded: the
        # test reads the database as soon as this returns. Not the first
        # submit button on the page either -- the related tabs carry their
        # own (hidden) action buttons.
        with page.expect_response(lambda r: r.request.method == "POST"):
            page.get_by_role("button", name="Save", exact=True).first.click()
        page.wait_for_load_state()
        expect(page.locator(".has-error")).to_have_count(0)
