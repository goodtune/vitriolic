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
    name: str
    brand: str
    base: str
    started: str = ""
    finished: str = ""
    pages: list[PageResult] = field(default_factory=list)
    flow: list[StepResult] = field(default_factory=list)

    @property
    def results(self) -> list[PageResult | StepResult]:
        return [*self.pages, *self.flow]

    @property
    def error_count(self) -> int:
        return sum(len(r.errors) for r in self.results)

    @property
    def warning_count(self) -> int:
        return sum(len(r.warnings) for r in self.results)

    @property
    def failed(self) -> bool:
        return self.error_count > 0

    def write(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def read(cls, path: Path) -> "Manifest":
        data = json.loads(Path(path).read_text())
        pages = [PageResult(**p) for p in data.pop("pages", [])]
        flow = [StepResult(**s) for s in data.pop("flow", [])]
        return cls(pages=pages, flow=flow, **data)
