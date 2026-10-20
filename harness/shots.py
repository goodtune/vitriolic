"""Capture every admin page at each width and record what went wrong.

The driver signs in as the seeded superuser, opens each page in
``<var>/state/<name>/pages.json`` and saves a full-page PNG per width. Pages
with tabs get one more PNG per tab. The manifest beside the images lists every
page, its HTTP status and the errors and warnings it raised; it is written
even when the run fails, and the exit status is 1 when any page errored.

What counts as an error: the page does not load, answers 4xx or 5xx, ends on
the sign-in page, logs a console ``error`` or an uncaught page error, or a
request to the server under test fails. A request to another host (a font, an
avatar, an image on a CDN) is only a warning, recorded with its URL.

Elements are found by role, accessible name, URL or form field name, never by
CSS class.

Usage: ``python -m harness.shots --name N --base URL [options]``. The
``shots.sh`` wrapper works out the base URL, checks the server and refreshes
``pages.json`` first.
"""

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from harness.manifest import Manifest, PageResult
from harness.paths import normalise, paths_for

logger = logging.getLogger(__name__)

LOGIN_PATH = "/admin/login/"
USERNAME = "admin"
PASSWORD = "password"

#: How long to wait for the network to go quiet before taking the picture.
SETTLE_MS = 3000
NAVIGATION_MS = 30000
CLICK_MS = 3000

#: Pages that also get a picture of the first screen only, at this width.
FOLD_PAGES = ("season-edit", "match-results")
FOLD_WIDTH = 1440

#: The scheme-and-host of a request decides whether a failure is an error.
LOCAL_SCHEMES = ("data", "blob", "about")


def prepare_out(out: Path, name: str, brand: str) -> None:
    """
    Make ``out`` ready for a run: create it, or clear what an earlier run of
    the same name and brand left. Anything else in it is not ours to delete.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    entries = list(out.iterdir())
    if not entries:
        return
    try:
        previous = Manifest.read(out / "manifest.json")
    except (OSError, ValueError, TypeError):
        previous = None
    if previous is None or (previous.name, previous.brand) != (name, brand):
        raise SystemExit(
            f"refusing to clear {out}: not a previous run of {name}/{brand}"
        )
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


class Collector:
    """What one page raises while it loads, split into errors and warnings."""

    def __init__(self, page: Page, host: str):
        self.host = host
        self.errors: list[str] = []
        self.warnings: list[str] = []
        page.on("console", self._console)
        page.on("pageerror", self._pageerror)
        page.on("requestfailed", self._requestfailed)

    def _same_host(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in LOCAL_SCHEMES or parsed.netloc == self.host

    def _add(self, bucket: list[str], message: str) -> None:
        if message not in bucket:
            bucket.append(message)

    def _console(self, message) -> None:
        if message.type != "error":
            return
        text = message.text
        url = message.location.get("url", "") if message.location else ""
        if text.startswith("Failed to load resource"):
            # Chromium also reports a subresource as a console error. A
            # network failure is already seen by _requestfailed; a response
            # with an error status is not, and its host decides how serious
            # it is.
            if "net::ERR_" not in text and url:
                bucket = self.errors if self._same_host(url) else self.warnings
                self._add(bucket, "%s: %s" % (text, url))
        else:
            self._add(self.errors, "console error: %s" % text)

    def _pageerror(self, error) -> None:
        self._add(self.errors, "uncaught page error: %s" % error)

    def _requestfailed(self, request) -> None:
        failure = request.failure or "failed"
        if "ERR_ABORTED" in failure:
            # The browser cancelled it (a stylesheet refused with a 404, a
            # navigation that moved on); a refusal shows as a console error.
            return
        bucket = self.errors if self._same_host(request.url) else self.warnings
        self._add(bucket, "request failed: %s (%s)" % (request.url, failure))

    def drain(self) -> tuple[list[str], list[str]]:
        errors, warnings = self.errors, self.warnings
        self.errors, self.warnings = [], []
        return errors, warnings


def settle(page: Page) -> None:
    """Wait for the network to go quiet, but never for long."""
    try:
        page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
    except PlaywrightTimeout:
        logger.debug("%s did not go idle in %d ms", page.url, SETTLE_MS)


def sign_in(page: Page, base: str) -> None:
    page.goto(base + LOGIN_PATH, wait_until="load", timeout=NAVIGATION_MS)
    page.locator('input[name="username"]').fill(USERNAME)
    page.locator('input[name="password"]').fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_load_state("load")
    if urlparse(page.url).path.startswith(LOGIN_PATH):
        raise RuntimeError(
            "signing in as %s left the page at %s" % (USERNAME, page.url)
        )


def tab_locators(page: Page) -> list[Locator]:
    """
    The tabs of the page, in the order they appear: every visible ``role=tab``,
    else every visible link to an anchor that exists on the page, except the
    skip-to-content link.
    """
    tabs = page.get_by_role("tab")
    candidates = [tabs.nth(i) for i in range(tabs.count())]
    if not candidates:
        links = page.locator('a[href^="#"]:not([href="#"])')
        for i in range(links.count()):
            link = links.nth(i)
            if link.inner_text().strip().lower().startswith("skip to"):
                continue
            target = (link.get_attribute("href") or "")[1:]
            if page.locator("[id=%s]" % json.dumps(target)).count():
                candidates.append(link)
    return [tab for tab in candidates if tab.is_visible()]


def _path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path + ("?" + parsed.query if parsed.query else "")


def capture_page(page, collector, base, spec, width, out) -> PageResult:
    """Load one page and save its full-page picture; returns the result."""
    name, url = spec["name"], spec["url"]
    errors: list[str] = []
    status, title, final_url = 0, "", ""
    try:
        response = page.goto(base + url, wait_until="load", timeout=NAVIGATION_MS)
        settle(page)
        status = response.status if response else 0
        title = page.title()
        final_url = _path(page.url)
        if status == 0 or status >= 400:
            errors.append("HTTP %d" % status)
        elif urlparse(page.url).path.startswith(LOGIN_PATH) and not url.startswith(
            LOGIN_PATH
        ):
            errors.append("redirected to sign-in")
        if width == FOLD_WIDTH and name in FOLD_PAGES:
            page.screenshot(path=str(out / ("%s-fold-%d.png" % (name, width))))
        page.screenshot(path=str(out / ("%s-%d.png" % (name, width))), full_page=True)
    except PlaywrightError as exc:
        errors.append("failed to load: %s" % str(exc).splitlines()[0])
    raised_errors, warnings = collector.drain()
    return PageResult(
        name=name,
        url=url,
        width=width,
        status=status,
        title=title,
        errors=errors + raised_errors,
        warnings=warnings,
        file="%s-%d.png" % (name, width),
        final_url="" if final_url == _path(url) else final_url,
    )


def capture_tabs(page, collector, spec, width, out, status, title):
    """One picture per tab of a tabbed page, in the order the tabs appear."""
    results = []
    tabs = tab_locators(page)
    for n in range(1, len(tabs) + 1):
        name = "%s-tab-%d" % (spec["name"], n)
        errors: list[str] = []
        file = "%s-%d.png" % (name, width)
        try:
            tabs[n - 1].click(timeout=CLICK_MS)
            settle(page)
            page.screenshot(path=str(out / file), full_page=True)
        except PlaywrightError as exc:
            errors.append("tab %d did not open: %s" % (n, str(exc).splitlines()[0]))
            file = ""
        raised_errors, warnings = collector.drain()
        results.append(
            PageResult(
                name=name,
                url=spec["url"],
                width=width,
                status=status,
                title=title,
                errors=errors + raised_errors,
                warnings=warnings,
                file=file,
            )
        )
    return results


def report(result: PageResult) -> None:
    flag = "ok" if not result.errors else "ERROR"
    if result.warnings:
        flag += " (%d warnings)" % len(result.warnings)
    print("%s %d %d %s" % (result.name, result.width, result.status, flag), flush=True)
    for message in result.errors:
        print("    error: %s" % message, flush=True)


def run(
    base: str,
    pages: list[dict],
    out: Path,
    widths: list[int],
    height: int,
    video: bool,
    only: set[str] | None,
    *,
    name: str = "",
    brand: str = "",
) -> Manifest:
    """
    Capture ``pages`` at each of ``widths`` and return the manifest, which is
    also written to ``out/manifest.json`` however the run ends.

    ``video`` is the switch the recorded flow uses; this function captures
    pictures only and leaves it alone.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    host = urlparse(base).netloc
    manifest = Manifest(
        name=name,
        brand=brand,
        base=base,
        started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    selected = [p for p in pages if only is None or p["name"] in only]
    # Written first as well as last, so that a run which is killed part way
    # still reads as a run of this name and brand when the next one clears it.
    manifest.write(out / "manifest.json")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for width in widths:
                    context = browser.new_context(
                        viewport={"width": width, "height": height}
                    )
                    try:
                        login_page = context.new_page()
                        sign_in(login_page, base)
                        login_page.close()
                    except (PlaywrightError, RuntimeError) as exc:
                        failure = PageResult(
                            name="sign-in",
                            url=LOGIN_PATH,
                            width=width,
                            status=0,
                            title="",
                            errors=["sign-in failed: %s" % str(exc).splitlines()[0]],
                        )
                        manifest.pages.append(failure)
                        report(failure)
                        context.close()
                        continue
                    for spec in selected:
                        page = context.new_page()
                        collector = Collector(page, host)
                        result = capture_page(page, collector, base, spec, width, out)
                        manifest.pages.append(result)
                        report(result)
                        if spec.get("tabs") and not result.errors:
                            for tab in capture_tabs(
                                page,
                                collector,
                                spec,
                                width,
                                out,
                                result.status,
                                result.title,
                            ):
                                manifest.pages.append(tab)
                                report(tab)
                        page.close()
                    context.close()
            finally:
                browser.close()
    finally:
        manifest.finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest.write(out / "manifest.json")
    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.shots")
    parser.add_argument("--name", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--brand", default="default")
    parser.add_argument("--widths", default="1440,390")
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--only", default="")
    parser.add_argument("--no-video", dest="video", action="store_false")
    parser.add_argument("--pages", type=Path)
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    name = normalise(args.name)
    paths = paths_for(name)
    out = args.out or paths["runs"] / args.brand
    pages_file = args.pages or paths["state"] / "pages.json"
    pages = json.loads(pages_file.read_text())["pages"]
    widths = [int(w) for w in args.widths.split(",") if w]
    only = {o for o in args.only.split(",") if o} or None

    prepare_out(out, name, args.brand)
    started = time.monotonic()
    manifest = run(
        args.base.rstrip("/"),
        pages,
        out,
        widths,
        args.height,
        args.video,
        only,
        name=name,
        brand=args.brand,
    )
    warned = sorted({w for r in manifest.results for w in r.warnings})
    for message in warned:
        print("warning: %s" % message)
    print(
        "shots: %d captures, %d errors, %d warnings in %.0f s -> %s"
        % (
            len(manifest.pages),
            manifest.error_count,
            manifest.warning_count,
            time.monotonic() - started,
            out,
        ),
        flush=True,
    )
    return 1 if manifest.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
