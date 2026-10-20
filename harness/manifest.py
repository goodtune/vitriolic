"""The record a screenshot run leaves beside its images.

``shots.py`` writes it, ``contact.py`` and the judging scripts read it. It is
written even when the run fails, so that the failure is on the record.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PageResult:
    """One page at one width."""

    name: str
    url: str
    width: int
    status: int
    title: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    file: str = ""
    #: Where the page ended after redirects; empty when it did not move.
    final_url: str = ""
    #: 0 for the page itself, n for the picture of its nth tab.
    tab: int = 0


@dataclass
class StepResult:
    """One step of the recorded flow at one width."""

    name: str
    width: int = 0
    #: Where the step ended.
    url: str = ""
    #: How the step got where it was going: "link" (followed what the page
    #: offers), "scroll" (the same, after scrolling the target into view) or
    #: "direct" (the address was typed because nothing on the page led there).
    via: str = "link"
    #: Why a step had to go "direct", or anything else worth knowing.
    note: str = ""
    status: str = "ok"
    #: Seconds the step took.
    duration: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    file: str = ""


@dataclass
class Manifest:
    """
    What a run captured, and enough about the run to tell a partial or stale
    set of pictures from a complete one.
    """

    name: str
    brand: str
    base: str
    #: The shell the server wore (``workbook`` or ``explorer``).
    shell: str = "workbook"
    started: str = ""
    finished: str = ""
    pages: list[PageResult] = field(default_factory=list)
    flow: list[StepResult] = field(default_factory=list)
    #: The page names ``--only`` asked for; ``None`` is every page.
    only: list[str] | None = None
    widths: list[int] = field(default_factory=list)
    #: Whether the flow was to be recorded.
    video: bool = True
    #: How many pages ``pages.json`` listed for the run.
    expected_pages: int = 0
    #: The checkout the run was made from, and its commit.
    checkout: str = ""
    commit: str = ""
    #: Whether the server loaded its tabs over HTMX.
    htmx_tabs: bool = False
    #: The stamp of the flow at each width, by width, for ``unflow``.
    flow_stamps: dict[str, str] = field(default_factory=dict)
    #: What went wrong with the run itself, before or between pages.
    errors: list[str] = field(default_factory=list)

    @property
    def results(self) -> list[PageResult | StepResult]:
        return [*self.pages, *self.flow]

    @property
    def error_count(self) -> int:
        return len(self.errors) + sum(len(r.errors) for r in self.results)

    @property
    def warning_count(self) -> int:
        return sum(len(r.warnings) for r in self.results)

    @property
    def captured(self) -> int:
        """How many pages were captured, counted once for each width."""
        return len(
            {
                (result.name, result.width)
                for result in self.pages
                if result.tab == 0 and result.file
            }
        )

    @property
    def incomplete(self) -> bool:
        """Fewer pages were captured than were listed, and no ``--only`` said why."""
        return self.only is None and self.captured < self.expected_pages * len(
            self.widths
        )

    @property
    def failed(self) -> bool:
        return self.error_count > 0 or self.incomplete

    def write(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def read(cls, path: Path) -> "Manifest":
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError("%s does not hold a manifest" % path)
        pages = [PageResult(**p) for p in data.pop("pages", [])]
        flow = [StepResult(**s) for s in data.pop("flow", [])]
        return cls(pages=pages, flow=flow, **data)
