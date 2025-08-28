"""Performance tests for Visual Scheduler with large datasets."""

import pytest
from datetime import date, time
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests.factories import (
    SeasonFactory,
    VenueFactory,
    GroundFactory,
    SeasonMatchTimeFactory,
)
from tournamentcontrol.competition.draw.schemas import DivisionStructure, StageFixture
from tournamentcontrol.competition.draw.builders import build
from tournamentcontrol.competition.utils import round_robin_format


class TestVisualSchedulerPerformance:
    """Performance tests for Visual Scheduler drag-and-drop operations."""

    @pytest.fixture
    def dataset(self, db):
        """Create test dataset with matches scheduled on grid."""
        season = SeasonFactory.create(timezone="Australia/Sydney")
        venue = VenueFactory.create(season=season)
        grounds = GroundFactory.create_batch(6, venue=venue)

        timeslot = SeasonMatchTimeFactory.create(
            season=season,
            start=time(8, 0),
            interval=30,
            count=20,
        )

        team_names = [f"Team {chr(65 + i)}" for i in range(8)]
        division_spec = DivisionStructure(
            title="Performance Test Division",
            teams=team_names,
            draw_formats={"round_robin": round_robin_format(8)},
            stages=[StageFixture(title="Round Robin", draw_format_ref="round_robin")],
        )

        division = build(season, division_spec)
        division.points_formula = "3*win + 2*draw + 1*loss"
        division.forfeit_for_score = 5
        division.forfeit_against_score = 0
        division.include_forfeits_in_played = True
        division.games_per_day = 2
        division.save()

        # Schedule all matches on grid
        time_ground_combinations = [
            (time_slot, ground) for time_slot in timeslot.rrule() for ground in grounds
        ]

        for match, (start_time, play_at) in zip(
            division.matches.all(),
            time_ground_combinations,
        ):
            match.date = date(2024, 6, 15)
            match.time = start_time
            match.play_at = play_at
            match.save()

        return season

    def test_visual_scheduler_load_time(
        self, authenticated_page: Page, live_server, dataset
    ):
        """Test Visual Scheduler page loads within 5 seconds."""
        page = authenticated_page
        season = dataset

        visual_scheduler_url = f"{live_server.url}/admin/fixja/competition/{season.competition.pk}/seasons/{season.pk}/20240615/visual-schedule/"

        start_time = page.evaluate("performance.now()")
        page.goto(visual_scheduler_url)
        expect(page.locator(".visual-schedule-container")).to_be_visible(timeout=10000)
        end_time = page.evaluate("performance.now()")

        load_time = end_time - start_time
        assert load_time < 5000, f"Load time {load_time}ms exceeded 5000ms"

    def test_drag_drop_performance(
        self, authenticated_page: Page, live_server, dataset
    ):
        """Test drag-and-drop completes within 1 second and stays under 10% CPU."""
        page = authenticated_page
        season = dataset

        visual_scheduler_url = f"{live_server.url}/admin/fixja/competition/{season.competition.pk}/seasons/{season.pk}/20240615/visual-schedule/"
        page.goto(visual_scheduler_url)
        expect(page.locator(".visual-schedule-container")).to_be_visible(timeout=10000)

        # Enable runtime domain for CPU profiling
        cdp = page.context.new_cdp_session(page)
        cdp.send("Runtime.enable")
        cdp.send("Profiler.enable")

        # Drag match from grid to unscheduled pane
        first_match = page.locator(".match-item.scheduled").first
        unscheduled_pane = page.locator(".match-sidebar")

        cdp.send("Profiler.start")
        start_time = page.evaluate("performance.now()")
        first_match.drag_to(unscheduled_pane)
        end_time = page.evaluate("performance.now()")
        profile = cdp.send("Profiler.stop")

        drag_time = end_time - start_time
        cpu_time = sum(node.get("hitCount", 0) for node in profile["profile"]["nodes"])
        cpu_utilization = (cpu_time / (drag_time * 1000)) * 100 if drag_time > 0 else 0

        assert drag_time < 1000, (
            f"Drag to unscheduled took {drag_time}ms, expected < 1000ms"
        )
        assert cpu_utilization < 10, (
            f"CPU utilization {cpu_utilization:.1f}% exceeded 10%"
        )

        # Drag another match to vacant grid cell
        second_match = page.locator(".match-item.scheduled").first
        vacant_cell = page.locator(".grid-cell:not(:has(.match-item))").first

        cdp.send("Profiler.start")
        start_time = page.evaluate("performance.now()")
        second_match.drag_to(vacant_cell)
        end_time = page.evaluate("performance.now()")
        profile = cdp.send("Profiler.stop")

        drag_time = end_time - start_time
        cpu_time = sum(node.get("hitCount", 0) for node in profile["profile"]["nodes"])
        cpu_utilization = (cpu_time / (drag_time * 1000)) * 100 if drag_time > 0 else 0

        assert drag_time < 1000, (
            f"Drag to vacant cell took {drag_time}ms, expected < 1000ms"
        )
        assert cpu_utilization < 10, (
            f"CPU utilization {cpu_utilization:.1f}% exceeded 10%"
        )
