"""
A ``SignatureField`` as a person uses it: sign in the box, see the strokes,
clear them, sign again and send the form.

The drawing is Signature Pad's, in the browser, so only a browser can test
it. The page is the acceptance form of ``example_app``.
"""

import base64
import io
import re

import pytest
from django.urls import reverse
from example_app.models import Acceptance
from PIL import Image
from playwright.sync_api import Page, expect


@pytest.fixture
def sign_url(live_server, settings):
    settings.ROOT_URLCONF = "example_app.urls"
    return live_server.url + reverse("sign")


def draw(page: Page, canvas, strokes):
    """Draw each stroke, a list of points as fractions of the box, with the mouse."""
    box = canvas.bounding_box()
    for stroke in strokes:
        points = [
            (box["x"] + x * box["width"], box["y"] + y * box["height"])
            for x, y in stroke
        ]
        page.mouse.move(*points[0])
        page.mouse.down()
        for point in points[1:]:
            page.mouse.move(*point, steps=6)
        page.mouse.up()


PNG_DATA_URL = re.compile(r"^data:image/png;base64,[A-Za-z0-9+/]+=*$")

# Something like a signature: a looping line, then a line under it.
SIGNATURE = [
    [
        (0.12, 0.62),
        (0.18, 0.25),
        (0.24, 0.7),
        (0.3, 0.35),
        (0.36, 0.68),
        (0.44, 0.4),
        (0.5, 0.66),
        (0.58, 0.3),
        (0.66, 0.6),
        (0.74, 0.45),
    ],
    [(0.1, 0.82), (0.3, 0.81), (0.55, 0.8), (0.8, 0.78)],
]


def ink(canvas):
    """How many pixels of the canvas are not its white background."""
    return canvas.evaluate(
        """canvas => {
            const data = canvas.getContext("2d")
                .getImageData(0, 0, canvas.width, canvas.height).data;
            let dark = 0;
            for (let i = 0; i < data.length; i += 4) {
                if (data[i] < 128) dark += 1;
            }
            return dark;
        }"""
    )


def test_signature_is_drawn_cleared_and_saved(
    page: Page, sign_url, transactional_db, screenshot_dir
):
    page.goto(sign_url)
    canvas = page.locator(".signature-field canvas")
    hidden = page.locator('input[name="signature"]')
    expect(canvas).to_be_visible()
    expect(hidden).to_have_value("")
    assert ink(canvas) == 0
    page.screenshot(path=screenshot_dir / "signature_field_empty.png", full_page=True)

    # Sending the form unsigned is refused, beside the field.
    page.get_by_label("Name").fill("Jordan Fairweather")
    page.get_by_role("button", name="Accept and sign").click()
    expect(page.locator(".errorlist li")).to_have_text("Please sign in the box.")
    expect(page.get_by_label("Name")).to_have_value("Jordan Fairweather")
    assert Acceptance.objects.count() == 0

    # The strokes show as they are drawn, and the input carries them.
    canvas = page.locator(".signature-field canvas")
    draw(page, canvas, SIGNATURE)
    assert ink(canvas) > 500
    expect(hidden).to_have_value(PNG_DATA_URL)
    page.screenshot(path=screenshot_dir / "signature_field_signed.png", full_page=True)

    # Clear empties the box and the input; then it is signed again.
    page.get_by_role("button", name="Clear").click()
    assert ink(canvas) == 0
    expect(hidden).to_have_value("")
    draw(page, canvas, SIGNATURE)
    sent = hidden.input_value()

    page.get_by_role("button", name="Accept and sign").click()
    expect(page.get_by_role("heading")).to_have_text("Signed by Jordan Fairweather")
    acceptance = Acceptance.objects.get()
    assert acceptance.signature == sent

    # What was kept is a PNG of the strokes, which the page shows as an image.
    image = Image.open(
        io.BytesIO(base64.b64decode(acceptance.signature.split(",", 1)[1]))
    )
    assert image.format == "PNG"
    dark = sum(1 for pixel in image.convert("L").getdata() if pixel < 128)
    assert dark > 500
    shown = page.get_by_alt_text("The signature of Jordan Fairweather")
    expect(shown).to_be_visible()
    assert shown.evaluate("img => img.naturalWidth") == image.width
    page.screenshot(path=screenshot_dir / "signature_field_saved.png", full_page=True)


def test_signature_is_kept_when_another_field_is_refused(
    page: Page, sign_url, transactional_db
):
    # The form comes back with the name's error; the signature is drawn again
    # from what was sent, and is sent again as it was.
    page.goto(sign_url)
    canvas = page.locator(".signature-field canvas")
    draw(page, canvas, SIGNATURE)
    sent = page.locator('input[name="signature"]').input_value()
    page.get_by_label("Name").evaluate("input => input.removeAttribute('required')")
    page.get_by_role("button", name="Accept and sign").click()
    expect(page.locator(".errorlist li")).to_have_text("This field is required.")

    canvas = page.locator(".signature-field canvas")
    expect(page.locator('input[name="signature"]')).to_have_value(sent)
    # The image is drawn once it has loaded, a moment after the page.
    page.wait_for_function(
        """() => {
            const canvas = document.querySelector(".signature-field canvas");
            const data = canvas.getContext("2d")
                .getImageData(0, 0, canvas.width, canvas.height).data;
            let dark = 0;
            for (let i = 0; i < data.length; i += 4) {
                if (data[i] < 128) dark += 1;
            }
            return dark > 500;
        }"""
    )
    page.get_by_label("Name").fill("Jordan Fairweather")
    page.get_by_role("button", name="Accept and sign").click()
    expect(page.get_by_role("heading")).to_have_text("Signed by Jordan Fairweather")
    assert Acceptance.objects.get().signature == sent


def test_signature_can_be_drawn_with_a_finger(browser, sign_url, screenshot_dir):
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
    )
    page = context.new_page()
    try:
        page.goto(sign_url)
        canvas = page.locator(".signature-field canvas")
        hidden = page.locator('input[name="signature"]')
        # The box is as wide as the phone allows, and a touch draws in it.
        box = canvas.bounding_box()
        assert box["width"] <= 390
        # Real touches, sent as the browser's own input, not made-up events.
        touch = context.new_cdp_session(page)
        for stroke in SIGNATURE:
            points = [
                {
                    "x": round(box["x"] + x * box["width"]),
                    "y": round(box["y"] + y * box["height"]),
                }
                for x, y in stroke
            ]
            touch.send(
                "Input.dispatchTouchEvent",
                {"type": "touchStart", "touchPoints": [points[0]]},
            )
            for point in points[1:]:
                # Signature Pad takes a point every 16 ms at most.
                page.wait_for_timeout(30)
                touch.send(
                    "Input.dispatchTouchEvent",
                    {"type": "touchMove", "touchPoints": [point]},
                )
            touch.send(
                "Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}
            )
        assert ink(canvas) > 500
        expect(hidden).to_have_value(PNG_DATA_URL)
        page.screenshot(path=screenshot_dir / "signature_field_phone.png")
    finally:
        context.close()
