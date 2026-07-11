"""E2E tests for the bulk live-stream toggle admin page."""

from datetime import date, time

import pytest
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests.factories import (
    DivisionFactory,
    GroundFactory,
    MatchFactory,
    SeasonFactory,
    StageFactory,
    TeamFactory,
    VenueFactory,
)


class TestMatchLiveStream:
    """Tests for the runsheet's bulk live-stream toggle page."""

    @pytest.fixture
    def live_stream_dataset(self, db):
        """
        Build matches whose time+field order deliberately contradicts
        their division order, so tests can prove rows are ordered by
        time then field -- not grouped or ordered by division.
        """
        season = SeasonFactory.create(timezone="Australia/Sydney")
        venue = VenueFactory.create(season=season)

        # Created in this order so ground_1.pk < ground_2.pk.
        ground_1 = GroundFactory.create(venue=venue, title="Court 1", live_stream=True)
        ground_2 = GroundFactory.create(venue=venue, title="Court 2", live_stream=True)

        division_alpha = DivisionFactory.create(season=season, title="Alpha Division")
        division_beta = DivisionFactory.create(season=season, title="Beta Division")

        stage_alpha = StageFactory.create(division=division_alpha, title="Stage 1")
        stage_beta = StageFactory.create(division=division_beta, title="Stage 1")

        team_alpha_1 = TeamFactory.create(division=division_alpha, title="Alpha One")
        team_alpha_2 = TeamFactory.create(division=division_alpha, title="Alpha Two")
        team_beta_1 = TeamFactory.create(division=division_beta, title="Beta One")
        team_beta_2 = TeamFactory.create(division=division_beta, title="Beta Two")

        match_day = date(2024, 6, 15)

        # 09:00 on Court 1 -- Beta division, should render FIRST.
        match_early_court1 = MatchFactory.create(
            stage=stage_beta,
            home_team=team_beta_1,
            away_team=team_beta_2,
            date=match_day,
            time=time(9, 0),
            play_at=ground_1,
        )
        # 09:00 on Court 2 -- Alpha division, should render SECOND
        # (same time as above, but a later field breaks the tie).
        match_early_court2 = MatchFactory.create(
            stage=stage_alpha,
            home_team=team_alpha_1,
            away_team=team_alpha_2,
            date=match_day,
            time=time(9, 0),
            play_at=ground_2,
        )
        # 11:00 on Court 1 -- Beta division again, should render LAST
        # despite matching match_early_court1's division and field.
        match_late_court1 = MatchFactory.create(
            stage=stage_beta,
            home_team=team_beta_2,
            away_team=team_beta_1,
            date=match_day,
            time=time(11, 0),
            play_at=ground_1,
        )

        return {
            "season": season,
            "match_day": match_day,
            "match_early_court1": match_early_court1,
            "match_early_court2": match_early_court2,
            "match_late_court1": match_late_court1,
        }

    def _live_stream_url(self, live_server, season, match_day):
        return (
            f"{live_server.url}/admin/fixja/competition/{season.competition.pk}"
            f"/seasons/{season.pk}/{match_day.strftime('%Y%m%d')}/live-stream/"
        )

    def test_rows_ordered_by_time_then_field(
        self, authenticated_page: Page, live_server, live_stream_dataset
    ):
        """Rows must be ordered by time then field, not by division."""
        page = authenticated_page
        data = live_stream_dataset

        page.goto(
            self._live_stream_url(live_server, data["season"], data["match_day"])
        )
        expect(page.locator(".live-stream-row")).to_have_count(3)

        row_texts = page.locator(".live-stream-row").all_inner_texts()

        # Expected order: 09:00/Court 1, 09:00/Court 2, 11:00/Court 1.
        assert "Alpha One vs Beta" not in row_texts[0]
        assert "9 a.m." in row_texts[0] and "Court 1" in row_texts[0]
        assert "Beta One" in row_texts[0] or "Beta Two" in row_texts[0]

        assert "9 a.m." in row_texts[1] and "Court 2" in row_texts[1]
        assert "Alpha One" in row_texts[1] or "Alpha Two" in row_texts[1]

        assert "11 a.m." in row_texts[2] and "Court 1" in row_texts[2]
        assert "Beta One" in row_texts[2] or "Beta Two" in row_texts[2]

    def test_row_shows_time_division_field_match_and_toggle(
        self, authenticated_page: Page, live_server, live_stream_dataset
    ):
        """Each row must show time, division, field, the match, and the toggle."""
        page = authenticated_page
        data = live_stream_dataset

        page.goto(
            self._live_stream_url(live_server, data["season"], data["match_day"])
        )

        first_row = page.locator(".live-stream-row").first
        expect(first_row).to_contain_text("9 a.m.")
        expect(first_row).to_contain_text("Beta Division")
        expect(first_row).to_contain_text("Court 1")
        expect(first_row).to_contain_text("Beta One")
        expect(first_row.locator("select")).to_be_visible()

    def test_desktop_and_mobile_layout(
        self, authenticated_page: Page, live_server, live_stream_dataset, screenshot_dir
    ):
        """
        Desktop: time/division/field/match sit on one line (table-like).
        Mobile: they stack onto separate lines, with the toggle staying
        to the right of the stacked block, and each match visually grouped.
        """
        page = authenticated_page
        data = live_stream_dataset

        page.goto(
            self._live_stream_url(live_server, data["season"], data["match_day"])
        )
        expect(page.locator(".live-stream-row")).to_have_count(3)

        # Desktop (conftest's default 1920x1080 viewport).
        page.screenshot(
            path=str(screenshot_dir / "live_stream_desktop.png"), full_page=True
        )

        first_row = page.locator(".live-stream-row").first
        time_box = first_row.locator(".row .row > div").nth(0).bounding_box()
        division_box = first_row.locator(".row .row > div").nth(1).bounding_box()
        select_box = first_row.locator("select").bounding_box()

        # On desktop, time and division sit on the same line.
        assert abs(time_box["y"] - division_box["y"]) < 5
        # The toggle sits to the right of the info block.
        assert select_box["x"] > division_box["x"]

        # Mobile viewport.
        page.set_viewport_size({"width": 375, "height": 812})
        page.screenshot(
            path=str(screenshot_dir / "live_stream_mobile.png"), full_page=True
        )

        first_row = page.locator(".live-stream-row").first
        time_box = first_row.locator(".row .row > div").nth(0).bounding_box()
        division_box = first_row.locator(".row .row > div").nth(1).bounding_box()
        field_box = first_row.locator(".row .row > div").nth(2).bounding_box()
        select_box = first_row.locator("select").bounding_box()

        # On mobile, time/division/field stack onto separate lines.
        assert division_box["y"] > time_box["y"]
        assert field_box["y"] > division_box["y"]
        # The toggle still sits to the right of the stacked block, roughly
        # vertically centered alongside it rather than pushed below it.
        assert select_box["x"] > time_box["x"]
        assert select_box["y"] < field_box["y"]
