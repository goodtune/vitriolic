"""
Set-up guidance: what an object still needs before it is ready, step by step.

A view puts a ``Setup`` in its context as ``setup`` and the edit page shows it:
a progress bar under the title naming the next step, and a Set-up tab listing
every step with what is done, what is missing, and a link to the page that
completes it. Pages further down the tree show
the same progress bar for the object they sit inside. Everything is worked out
on the server, so it reads the same
without scripts.
"""

from dataclasses import dataclass, field


@dataclass
class Step:
    label: str
    done: bool
    detail: str = ""
    url: str | None = None
    optional: bool = False
    next: bool = False


@dataclass
class Setup:
    """
    The steps for one object. ``here`` is false when the page belongs to
    something inside that object (a pool inside a stage inside a season): the
    page then shows only the progress bar, and ``url`` leads back to the full
    list on the object's own page.
    """

    title: str
    steps: list = field(default_factory=list)
    url: str = "#setup-tab"
    here: bool = True

    def __post_init__(self):
        following = next((s for s in self.steps if not s.done and not s.optional), None)
        if following is not None:
            following.next = True

    @property
    def required(self):
        return [s for s in self.steps if not s.optional]

    @property
    def done(self):
        return sum(1 for s in self.required if s.done)

    @property
    def total(self):
        return len(self.required)

    @property
    def percent(self):
        return round(100 * self.done / self.total) if self.total else 100

    @property
    def complete(self):
        return self.done == self.total

    @property
    def next_step(self):
        return next((s for s in self.steps if s.next), None)
