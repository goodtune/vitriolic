"""
End-to-end validation of the OpenStreetMap location picker on the venue admin
page: the stored location is shown as a marker, clicking the map moves the
marker and fills in the latitude, longitude and zoom inputs, and saving the
form stores the new "latitude,longitude,zoom" value.
"""

import pytest
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests.factories import VenueFactory


@pytest.fixture
def venue(db):
    return VenueFactory.create(
        title="Sydney Olympic Park", latlng="-33.847100,151.068500,15"
    )


def _inputs(page: Page):
    return [page.locator(f'input[name="latlng_{i}"]') for i in range(3)]


def test_location_widget_venue(
    authenticated_page: Page, live_server, venue, screenshot_dir
):
    page = authenticated_page
    page.goto(f"{live_server.url}{venue.urls['edit']}")

    widget = page.locator(".location-widget")
    expect(widget.locator(".leaflet-tile-loaded").first).to_be_visible()
    expect(widget.locator(".leaflet-marker-icon")).to_be_visible()
    latitude, longitude, zoom = _inputs(page)
    expect(latitude).to_have_value("-33.847100")
    expect(longitude).to_have_value("151.068500")
    expect(zoom).to_have_value("15")

    page.wait_for_load_state("networkidle")
    page.screenshot(
        path=str(screenshot_dir / "location_widget_venue.png"), full_page=True
    )

    # The marker sits in the middle of the map; click up and to the left of
    # it, which is further north (larger latitude) and further west.
    canvas = widget.locator(".location-widget-map")
    box = canvas.bounding_box()
    canvas.click(position={"x": box["width"] / 4, "y": box["height"] / 4})

    expect(latitude).not_to_have_value("-33.847100")
    new_latitude = float(latitude.input_value())
    new_longitude = float(longitude.input_value())
    assert new_latitude > -33.8471
    assert new_longitude < 151.0685
    expect(zoom).to_have_value("15")

    page.wait_for_load_state("networkidle")
    widget.screenshot(path=str(screenshot_dir / "location_widget_venue_moved.png"))

    page.get_by_role("button", name="Save").click()
    page.wait_for_load_state("networkidle")

    venue.refresh_from_db()
    assert venue.latlng == f"{new_latitude:.6f},{new_longitude:.6f},15"


def test_location_widget_inputs_move_map(authenticated_page: Page, live_server, venue):
    page = authenticated_page
    page.goto(f"{live_server.url}{venue.urls['edit']}")

    widget = page.locator(".location-widget")
    expect(widget.locator('img.leaflet-tile[src*="/15/"]').first).to_be_visible()

    latitude, longitude, zoom = _inputs(page)
    latitude.fill("-33.900000")
    longitude.fill("151.000000")
    zoom.fill("12")
    zoom.dispatch_event("change")

    # Typing a position recentres the map at the typed zoom level, so it
    # loads zoom 12 tiles and keeps the marker in the middle of the map.
    expect(widget.locator('img.leaflet-tile[src*="/12/"]').first).to_be_visible()
    canvas = widget.locator(".location-widget-map").bounding_box()
    marker = widget.locator(".leaflet-marker-icon").bounding_box()
    assert (
        abs(marker["x"] + marker["width"] / 2 - (canvas["x"] + canvas["width"] / 2)) < 2
    )
