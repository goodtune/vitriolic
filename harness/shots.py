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
CSS class. The sign-in page is photographed first, before anyone has signed
in. Every page that has tabs (a ``role=tab`` control, a link in a
``role=tablist``, or two or more links to anchors of the page) gets one more
picture per tab, whether discovery marked it as tabbed or not; a page marked
as tabbed that has none records a warning.

Usage: ``python -m harness.shots --name N --base URL [options]``. The
``shots.sh`` wrapper works out the base URL, checks the server and refreshes
``pages.json`` first.
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import (
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeout,
    sync_playwright,
)

from harness import flow
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


def prepare_out(
    out: Path,
    name: str,
    brand: str,
    htmx_tabs: bool = False,
    shell: str = "workbook",
) -> None:
    """
    Make ``out`` ready for a run: create it, or clear what an earlier run of
    the same name, brand, shell and tab mode left. Anything else in it is not ours to
    delete.
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
    if previous is None or (
        previous.name,
        previous.brand,
        previous.shell,
        previous.htmx_tabs,
    ) != (name, brand, shell, htmx_tabs):
        raise SystemExit(
            f"refusing to clear {out}: not a previous run of {name}/{brand}/{shell}"
            + (" with HTMX tabs" if htmx_tabs else "")
        )
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def head_commit(checkout: Path) -> str:
    """The commit the checkout is at, or ``unknown``."""
    try:
        done = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return (
        done.stdout.strip()
        if done.returncode == 0 and done.stdout.strip()
        else "unknown"
    )


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
            if "net::ERR_" not in text:
                if url:
                    bucket = self.errors if self._same_host(url) else self.warnings
                    self._add(bucket, f"{text}: {url}")
                else:
                    # With no address there is no host to excuse it.
                    self._add(self.errors, f"console error: {text}")
        else:
            self._add(self.errors, f"console error: {text}")

    def _pageerror(self, error) -> None:
        self._add(self.errors, f"uncaught page error: {error}")

    def _requestfailed(self, request) -> None:
        failure = request.failure or "failed"
        if "ERR_ABORTED" in failure:
            # The browser cancelled it (a stylesheet refused with a 404, a
            # navigation that moved on); a refusal shows as a console error.
            return
        bucket = self.errors if self._same_host(request.url) else self.warnings
        self._add(bucket, f"request failed: {request.url} ({failure})")

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
        raise RuntimeError(f"signing in as {USERNAME} left the page at {page.url}")


def tab_locators(page: Page) -> list[Locator]:
    """
    The tabs of the page, in the order they appear: every visible ``role=tab``;
    else every visible link in a ``role=tablist``; else, when there are at
    least two, every visible link to an anchor that exists on the page, except
    the skip-to-content link.
    """
    tabs = page.get_by_role("tab").filter(visible=True)
    if tabs.count():
        return [tabs.nth(i) for i in range(tabs.count())]
    listed = page.get_by_role("tablist").get_by_role("link").filter(visible=True)
    if listed.count():
        return [listed.nth(i) for i in range(listed.count())]
    candidates = []
    links = page.locator('a[href^="#"]:not([href="#"])').filter(visible=True)
    for i in range(links.count()):
        link = links.nth(i)
        if link.inner_text().strip().lower().startswith("skip to"):
            continue
        target = (link.get_attribute("href") or "")[1:]
        if page.locator(f"[id={json.dumps(target)}]").count():
            candidates.append(link)
    return candidates if len(candidates) >= 2 else []


def _path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path + ("?" + parsed.query if parsed.query else "")


def capture_page(page, collector, base, spec, width, out) -> PageResult:
    """Load one page and save its full-page picture; returns the result."""
    name, url = spec["name"], spec["url"]
    errors: list[str] = []
    status, title, final_url = 0, "", ""
    saved = False
    try:
        response = page.goto(base + url, wait_until="load", timeout=NAVIGATION_MS)
        settle(page)
        status = response.status if response else 0
        title = page.title()
        final_url = _path(page.url)
        if status == 0 or status >= 400:
            errors.append(f"HTTP {status}")
        elif name == "login" and final_url != _path(url):
            errors.append(f"the sign-in page redirected to {final_url}")
        elif urlparse(page.url).path.startswith(LOGIN_PATH) and not url.startswith(
            LOGIN_PATH
        ):
            errors.append("redirected to sign-in")
        if width == FOLD_WIDTH and name in FOLD_PAGES:
            page.screenshot(path=str(out / f"{name}-fold-{width}.png"))
        page.screenshot(path=str(out / f"{name}-{width}.png"), full_page=True)
        saved = True
    except PlaywrightError as exc:
        errors.append(f"failed to load: {str(exc).splitlines()[0]}")
    raised_errors, warnings = collector.drain()
    return PageResult(
        name=name,
        url=url,
        width=width,
        status=status,
        title=title,
        errors=errors + raised_errors,
        warnings=warnings,
        file=f"{name}-{width}.png" if saved else "",
        final_url="" if final_url == _path(url) else final_url,
    )


def capture_tabs(page, collector, spec, width, out, status, title):
    """
    One picture per tab of a page, in the order the tabs appear, named
    ``<page>-tab-<n>-<width>.png``. A page that discovery marked as tabbed and
    that has no tabs gets a warning in a result of its own.
    """
    results = []
    tabs = tab_locators(page)
    if not tabs and spec.get("tabs"):
        results.append(
            PageResult(
                name=f"{spec['name']}-tab-0",
                url=spec["url"],
                width=width,
                status=status,
                title=title,
                warnings=["no tabs found"],
                tab=0,
            )
        )
    for n in range(1, len(tabs) + 1):
        name = f"{spec['name']}-tab-{n}"
        errors: list[str] = []
        file = f"{name}-{width}.png"
        try:
            tabs[n - 1].click(timeout=CLICK_MS)
            settle(page)
            page.screenshot(path=str(out / file), full_page=True)
        except PlaywrightError as exc:
            errors.append(f"tab {n} did not open: {str(exc).splitlines()[0]}")
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
                tab=n,
            )
        )
    return results


def report(result: PageResult) -> None:
    flag = "ok" if not result.errors else "ERROR"
    if result.warnings:
        flag += f" ({len(result.warnings)} warnings)"
    print(f"{result.name} {result.width} {result.status} {flag}", flush=True)
    for message in result.errors:
        print(f"    error: {message}", flush=True)


def capture_spec(context, host, base, spec, width, out, manifest) -> None:
    """
    Capture one page, and its tabs, in a page of its own, and add the results
    to ``manifest``. Anything the browser raises on the way is recorded as an
    error of that page and the run goes on to the next.
    """
    page = None
    try:
        page = context.new_page()
        collector = Collector(page, host)
        result = capture_page(page, collector, base, spec, width, out)
        manifest.pages.append(result)
        report(result)
        if not result.errors:
            for tab in capture_tabs(
                page, collector, spec, width, out, result.status, result.title
            ):
                manifest.pages.append(tab)
                report(tab)
    except PlaywrightError as exc:
        failure = PageResult(
            name=spec["name"],
            url=spec["url"],
            width=width,
            status=0,
            title="",
            errors=[f"capture failed: {str(exc).splitlines()[0]}"],
        )
        manifest.pages.append(failure)
        report(failure)
    finally:
        if page is not None:
            try:
                page.close()
            except PlaywrightError:
                logger.debug("could not close the page of %s", spec["name"])


def run(
    base: str,
    pages: list[dict],
    out: Path,
    height: int,
    manifest: Manifest,
) -> Manifest:
    """
    Capture ``pages`` at each of ``manifest.widths`` and add what happened to
    ``manifest``, which is also written to ``out/manifest.json`` however the
    run ends.

    The sign-in page is photographed first, before anyone has signed in; the
    other pages follow, signed in as the seeded superuser. ``manifest.only``
    limits the pages to those it names; an empty list captures none. When
    ``manifest.video`` is true the administrator's errand (``harness.flow``)
    then runs once per width, recorded to ``flow-<width>.webm``.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    host = urlparse(base).netloc
    manifest_path = out / "manifest.json"
    only = None if manifest.only is None else set(manifest.only)
    selected = [p for p in pages if only is None or p["name"] in only]
    signed_out = [p for p in selected if p["name"] == "login"]
    signed_in = [p for p in selected if p["name"] != "login"]
    # Written first as well as last, so that a run which is killed part way
    # still reads as a run of this name and brand when the next one clears it.
    manifest.write(manifest_path)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for width in manifest.widths if selected else []:
                    capture_width(
                        browser,
                        host,
                        base,
                        signed_out,
                        signed_in,
                        width,
                        height,
                        out,
                        manifest,
                    )
                    manifest.write(manifest_path)
                if manifest.video:
                    for width in manifest.widths:
                        record_flow(browser, base, host, manifest, out, width, height)
            finally:
                browser.close()
    finally:
        manifest.finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest.write(manifest_path)
    return manifest


def capture_width(
    browser, host, base, signed_out, signed_in, width, height, out, manifest
) -> None:
    """The pages at one width: the sign-in page first, then the rest signed in."""
    context = browser.new_context(viewport={"width": width, "height": height})
    try:
        for spec in signed_out:
            capture_spec(context, host, base, spec, width, out, manifest)
        if not signed_in:
            return
        page = context.new_page()
        collector = Collector(page, host)
        try:
            sign_in(page, base)
        except (PlaywrightError, RuntimeError) as exc:
            failure = PageResult(
                name="sign-in",
                url=LOGIN_PATH,
                width=width,
                status=0,
                title="",
                errors=[f"sign-in failed: {str(exc).splitlines()[0]}"],
            )
            manifest.pages.append(failure)
            report(failure)
            return
        # What the sign-in itself raised, which the pages after it do not show.
        raised, warnings = collector.drain()
        if raised or warnings:
            result = PageResult(
                name="sign-in",
                url=LOGIN_PATH,
                width=width,
                status=200,
                title="",
                errors=raised,
                warnings=warnings,
            )
            manifest.pages.append(result)
            report(result)
        page.close()
        for spec in signed_in:
            capture_spec(context, host, base, spec, width, out, manifest)
    finally:
        context.close()


def record_flow(browser, base, host, manifest, out, width, height) -> None:
    """
    Run the flow at ``width`` in a context of its own that records a video,
    and keep the video as ``flow-<width>.webm`` however the flow ends.
    """
    context = browser.new_context(
        viewport={"width": width, "height": height},
        record_video_dir=str(out),
        record_video_size={"width": width, "height": height},
    )
    page = context.new_page()
    video = page.video
    collector = Collector(page, host)
    try:
        flow.run(
            page,
            base,
            manifest,
            width,
            collector,
            checkpoint=lambda: manifest.write(out / "manifest.json"),
        )
    finally:
        context.close()
        if video is not None:
            video.save_as(str(out / f"flow-{width}.webm"))
            video.delete()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.shots")
    parser.add_argument("--name", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--brand", required=True)
    parser.add_argument(
        "--shell",
        default="workbook",
        choices=("workbook", "explorer"),
        help="the shell the server wears; the run goes in <brand>-<shell>",
    )
    parser.add_argument(
        "--htmx-tabs",
        action="store_true",
        help="the server loads its tabs over HTMX; the run goes in <brand>-htmx",
    )
    parser.add_argument("--widths", default="1440,390")
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument(
        "--only",
        default="",
        help="page names to capture, or 'none' to run the flow alone",
    )
    parser.add_argument("--no-video", dest="video", action="store_false")
    parser.add_argument("--pages", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="only clear the run directory and write the start manifest",
    )
    parser.add_argument(
        "--fail",
        metavar="MESSAGE",
        help="record that the run could not start, with this message",
    )
    return parser.parse_args(argv)


def select_pages(only: str, pages: list[dict]) -> set[str] | None:
    """
    The page names ``--only`` asks for: ``None`` for every page, an empty set
    for the sentinel ``none``. A name that is not a page is an error, so that
    a misspelt name does not quietly capture nothing.
    """
    if only == "none":
        return set()
    wanted = {o for o in only.split(",") if o}
    unknown = sorted(wanted - {p["name"] for p in pages})
    if unknown:
        raise SystemExit(f"unknown page name(s) in --only: {', '.join(unknown)}")
    return wanted or None


def parse_only(text: str) -> list[str] | None:
    """What ``--only`` says, as the manifest records it: ``None`` for every page."""
    if text == "none":
        return []
    names = sorted({name for name in text.split(",") if name})
    return names or None


def run_directory(name: str, brand: str, shell: str, htmx_tabs: bool) -> Path:
    """
    Where a run of ``name`` goes: ``<brand>-<shell>``, and ``<brand>-<shell>-htmx``
    for HTMX tabs.
    """
    suffix = "-htmx" if htmx_tabs else ""
    return paths_for(name)["runs"] / f"{brand}-{shell}{suffix}"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    name = normalise(args.name)
    out = args.out or run_directory(name, args.brand, args.shell, args.htmx_tabs)
    widths = [int(w) for w in args.widths.split(",") if w]

    # Before anything else, so that a run which fails early leaves an empty
    # directory and its start manifest, never the pictures of an earlier run.
    prepare_out(out, name, args.brand, args.htmx_tabs, args.shell)
    checkout = Path(__file__).resolve().parents[1]
    manifest_path = out / "manifest.json"
    manifest = Manifest(
        name=name,
        brand=args.brand,
        shell=args.shell,
        base=args.base.rstrip("/"),
        started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        widths=widths,
        video=args.video,
        checkout=str(checkout),
        commit=head_commit(checkout),
        htmx_tabs=args.htmx_tabs,
        only=parse_only(args.only),
    )
    if args.fail:
        manifest.errors.append(args.fail)
        manifest.finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest.write(manifest_path)
        print(f"shots: {args.fail}", file=sys.stderr)
        return 1
    manifest.write(manifest_path)
    if args.prepare:
        return 0

    started = time.monotonic()
    try:
        pages_file = args.pages or paths_for(name)["state"] / "pages.json"
        pages = json.loads(pages_file.read_text())["pages"]
        manifest.expected_pages = len(pages)
        only = select_pages(args.only, pages)
        if not args.video and only is not None and not only:
            raise SystemExit(
                "nothing to do: --only none leaves only the flow, and --no-video skips it"
            )
    except (OSError, ValueError, KeyError, SystemExit) as exc:
        manifest.errors.append(f"the run could not start: {exc}")
        manifest.finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest.write(manifest_path)
        raise
    manifest.only = None if only is None else sorted(only)

    manifest = run(args.base.rstrip("/"), pages, out, args.height, manifest)
    warned = sorted({w for r in manifest.results for w in r.warnings})
    for message in warned:
        print(f"warning: {message}")
    elapsed = time.monotonic() - started
    print(
        f"shots: {len(manifest.pages)} captures, {manifest.error_count} errors, "
        f"{manifest.warning_count} warnings in {elapsed:.0f} s -> {out}",
        flush=True,
    )
    if manifest.incomplete:
        print(
            f"shots: incomplete: {manifest.captured} of {manifest.expected_pages} "
            f"pages captured at {len(manifest.widths)} widths",
            flush=True,
        )
    return 1 if manifest.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
