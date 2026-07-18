"""E2E tests for the adhoc live stream event admin forms."""

import pytest
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests.factories import (
    LiveStreamEventFactory,
    LiveStreamKeyFactory,
    SeasonFactory,
)


class TestLiveStreamEventForm:
    """Tests for the season live stream event add/edit form.

    The scheduled start and finish are entered with individual component
    selects (year/month/day/hour/minute) and there is deliberately no
    timezone input -- times are implied to be in the season's timezone.
    """

    @pytest.fixture
    def live_stream_season(self, db):
        """A live-streamed season with a managed stream key and one event."""
        season = SeasonFactory.create(
            title="Test Season",
            timezone="Australia/Sydney",
            live_stream=True,
        )
        stream_key = LiveStreamKeyFactory.create(
            season=season, title="Roaming Camera"
        )
        event = LiveStreamEventFactory.create(
            season=season,
            title="Opening Ceremony",
            stream_key=stream_key,
        )
        return {"season": season, "stream_key": stream_key, "event": event}

    def _season_url(self, live_server, season):
        return (
            f"{live_server.url}/admin/fixja/competition/"
            f"{season.competition.pk}/seasons/{season.pk}/"
        )

    def test_season_edit_shows_live_stream_tabs(
        self, authenticated_page: Page, live_server, live_stream_season, screenshot_dir
    ):
        """
        The season edit page must offer the "Live stream events" and
        "Stream keys" tabs when the season has live streaming enabled.
        """
        page = authenticated_page
        season = live_stream_season["season"]

        page.goto(self._season_url(live_server, season))

        expect(page.locator('a[href="#live_stream_events-tab"]')).to_be_attached()
        expect(page.locator('a[href="#live_stream_keys-tab"]')).to_be_attached()

        page.locator('a[href="#live_stream_events-tab"]').click()
        expect(page.locator("#live_stream_events-tab")).to_contain_text(
            "Opening Ceremony"
        )
        page.screenshot(
            path=str(screenshot_dir / "live_stream_event_season_tab.png"),
            full_page=True,
        )

    def test_event_form_uses_component_selects_without_timezone(
        self, authenticated_page: Page, live_server, live_stream_season, screenshot_dir
    ):
        """
        The add form must present the scheduled start and finish as
        component selects, with no timezone input and help text naming
        the season's (implied) timezone.
        """
        page = authenticated_page
        season = live_stream_season["season"]

        page.goto(self._season_url(live_server, season) + "live-stream-event/add/")

        # Date and time entry is via selects, not text inputs.
        for prefix in ("start", "stop"):
            expect(page.locator(f'select[name="{prefix}_0_year"]')).to_be_visible()
            expect(page.locator(f'select[name="{prefix}_0_month"]')).to_be_visible()
            expect(page.locator(f'select[name="{prefix}_0_day"]')).to_be_visible()
            expect(page.locator(f'select[name="{prefix}_1"]')).to_be_visible()
            expect(page.locator(f'select[name="{prefix}_2"]')).to_be_visible()
            # No timezone component is offered.
            expect(page.locator(f'select[name="{prefix}_3"]')).to_have_count(0)

        # The implied timezone is stated to the user.
        expect(page.locator("form")).to_contain_text(
            "Local time in Australia/Sydney."
        )

        # The stream key drop-down offers the season's managed pool.
        expect(page.locator('select[name="stream_key"]')).to_contain_text(
            "Roaming Camera"
        )

        # Layout: the date components share one line, the time components
        # the next, rather than each select stacking full width.
        day = page.locator('select[name="start_0_day"]').bounding_box()
        month = page.locator('select[name="start_0_month"]').bounding_box()
        year = page.locator('select[name="start_0_year"]').bounding_box()
        hour = page.locator('select[name="start_1"]').bounding_box()
        minute = page.locator('select[name="start_2"]').bounding_box()

        assert abs(day["y"] - month["y"]) < 5
        assert abs(month["y"] - year["y"]) < 5
        assert abs(hour["y"] - minute["y"]) < 5
        assert hour["y"] > day["y"]

        page.screenshot(
            path=str(screenshot_dir / "live_stream_event_form.png"), full_page=True
        )

    def test_edit_form_renders_times_in_season_timezone(
        self, authenticated_page: Page, live_server, live_stream_season, screenshot_dir
    ):
        """
        Editing an existing event must render its scheduled times
        season-local in the component selects.
        """
        page = authenticated_page
        season = live_stream_season["season"]
        event = live_stream_season["event"]

        page.goto(
            self._season_url(live_server, season)
            + f"live-stream-event/{event.pk}/"
        )

        start_local = event.start.astimezone(season.timezone)
        expect(page.locator('select[name="start_0_year"]')).to_have_value(
            str(start_local.year)
        )
        expect(page.locator('select[name="start_1"]')).to_have_value(
            str(start_local.hour)
        )
        expect(page.locator('select[name="start_2"]')).to_have_value(
            str(start_local.minute)
        )

        page.screenshot(
            path=str(screenshot_dir / "live_stream_event_form_edit.png"),
            full_page=True,
        )
