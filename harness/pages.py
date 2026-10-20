"""Discover the admin pages the screenshot run captures.

Nothing here is a hand-written list of slugs. The pages come from the admin
site's registered components, from the admin URLs every ``AdminUrlMixin``
model describes for itself, and from the named routes of the competition
component that no model owns. No request is made: every URL is reversed. A
model or route that gives no page is listed under ``skipped`` with the reason,
never only logged.

``python -m harness pages [name]`` writes the result to
``<var>/state/<name>/pages.json``. The name defaults to the one the database
is named for (``vitriolic_<name>``), so it needs nothing beyond what
``harness_env`` exports.
"""

import json
import logging
import sys
from collections import Counter

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Count
from django.urls import NoReverseMatch, reverse

from harness.paths import database_name, normalise, paths_for
from touchtechnology.admin.mixins import AdminUrlMixin
from touchtechnology.admin.sites import site
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from tournamentcontrol.competition.models import (
    Club,
    Division,
    Match,
    Season,
    Stage,
    Team,
)
from tournamentcontrol.competition.utils import (
    legitimate_bye_match,
    match_unplayed,
    team_needs_progressing,
)

logger = logging.getLogger(__name__)

#: The season to capture is the one in progress: its title starts with this.
CURRENT_SEASON_PREFIX = "Spring"

#: Pages whose edit form has tabs; the screenshot driver clicks each one.
TABBED = {
    "season-edit",
    "division-edit",
    "club-edit",
    "classgroup-edit",
    "enrolment-edit",
}

#: The kinds of page a model gives, each the name of a URL in its namespace.
MODEL_VIEWS = ("edit", "add", "perms")


def _season():
    return (
        Season.objects.filter(title__startswith=CURRENT_SEASON_PREFIX)
        .order_by("pk")
        .first()
    )


def _division():
    season = _season()
    if season is None:
        return None
    return (
        Division.objects.filter(season=season)
        .annotate(team_count=Count("teams"))
        .order_by("-team_count", "pk")
        .first()
    )


def pick(model):
    """
    The one instance of ``model`` to capture, or ``None`` when there is none.

    The current season, its busiest division, a played match with a result
    and the round robin stage are chosen on purpose; every other model gives
    its first row.
    """
    season = _season()
    if model is Season:
        return season
    if model is Division:
        return _division()
    if model is Match:
        return (
            Match.objects.filter(
                stage__division__season=season,
                is_bye=False,
                is_forfeit=False,
                home_team_score__isnull=False,
                away_team_score__isnull=False,
            )
            .order_by("pk")
            .first()
        )
    if model is Stage:
        return (
            Stage.objects.filter(division=_division(), keep_ladder=True)
            .order_by("pk")
            .first()
        )
    return model._base_manager.order_by("pk").first()


def _models():
    """The models with admin URLs, in a stable order, and their page names."""
    models = sorted(
        (m for m in apps.get_models() if issubclass(m, AdminUrlMixin)),
        key=lambda m: m._meta.label,
    )
    counts = Counter(m._meta.model_name for m in models)
    return [
        (m, m._meta.model_name if counts[m._meta.model_name] == 1 else m._meta.label)
        for m in models
    ]


def _reverse(url_name, args=()):
    return str(reverse(url_name, args=args))


def _page(name, url, kind, **extra):
    page = {"name": name, "url": url, "kind": kind}
    if name in TABBED:
        page["tabs"] = True
    page.update(extra)
    return page


def _model_pages(model, name):
    """
    Returns ``(pages, reason)``: the pages of one model, or why it has none.
    """
    instance = pick(model)
    if instance is None:
        return [], "no instance to open in the seeded database"

    # Any model may describe its URLs badly, and an entry may change what its
    # admin.py does, so whatever goes wrong is a reason and not a crash.
    try:
        lookups = instance.url_names
        edit = lookups["edit"]
        edit_url = _reverse(edit.url_name, edit.args)
    except Exception as exc:  # noqa: BLE001
        return [], "the edit URL does not reverse: %s: %s" % (
            type(exc).__name__,
            str(exc) or "no message",
        )

    pages = [_page("%s-edit" % name, edit_url, "edit")]

    # The routes that take a parent's arguments only: the new instance has no
    # primary key, so the parent is every argument but the last.
    parent = list(edit.args[:-1])
    add = lookups.get("add")
    if add is not None:
        try:
            pages.append(
                _page(
                    "%s-add" % name,
                    _reverse(add.url_name, parent),
                    "add",
                )
            )
        except NoReverseMatch as exc:
            logger.info("%s has no add page: %s", name, exc)

    perms = lookups.get("perms")
    if perms is not None:
        try:
            pages.append(
                _page(
                    "%s-perms" % name,
                    _reverse(perms.url_name, perms.args),
                    "perms",
                )
            )
        except NoReverseMatch as exc:
            logger.info("%s has no perms page: %s", name, exc)

    namespace = edit.url_name.rsplit(":", 1)[0]
    for args in ((), parent):
        try:
            pages.append(
                _page("%s-list" % name, _reverse("%s:list" % namespace, args), "list")
            )
            break
        except NoReverseMatch:
            continue

    return pages, None


#: What a node kind is called in a page name when its content type's name
#: would mislead: a node whose object is a ``Placeholder`` is an application.
NODE_KINDS = {"placeholder": "application"}


def _node_pages():
    """
    Returns ``(pages, skipped)`` for the site tree: one node of each kind
    (page, folder, application).

    ``SitemapNode`` is not an ``AdminUrlMixin`` model, it describes its admin
    URLs in its own ``urls``, which has no add page; that lives at the root of
    the kind's namespace.
    """
    pages = []
    skipped = []
    seen = set()
    for node in SitemapNode.objects.select_related("content_type").order_by("pk"):
        try:
            content_name = node.content_type.name
        except AttributeError:
            content_name = "folder"
        if content_name in seen:
            continue
        seen.add(content_name)
        name = NODE_KINDS.get(content_name, content_name)
        try:
            urls = node.urls
            edit_url = str(urls["edit"])
        except Exception as exc:  # noqa: BLE001
            skipped.append(
                {
                    "model": "SitemapNode (%s)" % name,
                    "reason": "the edit URL does not reverse: %s: %s"
                    % (type(exc).__name__, str(exc) or "no message"),
                }
            )
            continue
        pages.append(_page("%s-edit" % name, edit_url, "edit"))
        for view in ("add", "perms"):
            try:
                if view == "add":
                    url = _reverse("admin:content:%s:add" % content_name)
                else:
                    url = str(urls[view])
            except Exception as exc:  # noqa: BLE001
                logger.info("%s has no %s page: %s", name, view, exc)
            else:
                pages.append(_page("%s-%s" % (name, view), url, view))
    return pages, skipped


def _content_pages():
    """
    The content component's routes that no model mixin describes: the
    application configurations (``Placeholder`` rows) and the file manager.
    """
    pages = []
    skipped = []

    def add(name, kind, make):
        try:
            pages.append(_page(name, make(), kind))
        except NoReverseMatch as exc:
            skipped.append({"model": name, "reason": "does not reverse: %s" % exc})

    add(
        "placeholder-list",
        "list",
        lambda: _reverse("admin:content:real_placeholder:list"),
    )
    add(
        "placeholder-add", "add", lambda: _reverse("admin:content:real_placeholder:add")
    )
    placeholder = Placeholder.objects.order_by("pk").first()
    if placeholder is not None:
        add(
            "placeholder-edit",
            "edit",
            lambda: _reverse("admin:content:real_placeholder:edit", [placeholder.pk]),
        )
    else:
        skipped.append(
            {
                "model": "Placeholder",
                "reason": "no instance to open in the seeded database",
            }
        )
    add("media-list", "list", lambda: _reverse("admin:content:media:list"))
    return pages, skipped


def _static_pages():
    pages = [
        _page("index", _reverse("admin:index"), "static"),
        _page("login", _reverse("admin:login"), "static"),
    ]
    for __, app_name, url, __, __ in site.get_components():
        pages.append(_page("%s-index" % app_name, str(url), "static"))
    # The console admin's search across every kind of object, with a query
    # that finds a season, divisions, teams and a place of the menu.
    try:
        jump = _reverse("admin:jump")
    except NoReverseMatch:
        jump = None
    if jump:
        pages.append(_page("jump", jump + "?q=open", "static"))
    return pages


def _auth_pages():
    user = get_user_model().objects.order_by("pk").first()
    group = Group.objects.order_by("pk").first()
    pages = [
        _page("user-list", _reverse("admin:auth:users:list"), "list"),
        _page("group-list", _reverse("admin:auth:groups:list"), "list"),
    ]
    if user is not None:
        pages.append(
            _page("user-edit", _reverse("admin:auth:users:edit", [user.pk]), "edit")
        )
    if group is not None:
        pages.append(
            _page("group-edit", _reverse("admin:auth:groups:edit", [group.pk]), "edit")
        )
    return pages


def _next_match_day(season):
    """The earliest date in the season with a match still to be played."""
    return (
        Match.objects.filter(stage__division__season=season, date__isnull=False)
        .filter(match_unplayed)
        .exclude(is_bye=True)
        .order_by("date")
        .values_list("date", flat=True)
        .first()
    )


def _progress_variant(stage):
    """
    Which page ``progress`` gives for the stage: ``teams`` to name undecided
    teams, ``matches`` to resolve the rest, or ``None`` when it has nothing
    to progress (the view then answers 410 Gone).
    """
    matches = stage.matches.filter(team_needs_progressing).exclude(legitimate_bye_match)
    if not matches.exists():
        return None

    def resolvable(match):
        home_team, away_team = match.eval(lazy=True)
        return (match.home_team is None and isinstance(home_team, Team)) or (
            match.away_team is None and isinstance(away_team, Team)
        )

    undecided = matches.filter(
        home_team_undecided__isnull=False, home_team__isnull=True
    ) | matches.filter(away_team_undecided__isnull=False, away_team__isnull=True)
    if undecided.exists() and not any(resolvable(match) for match in matches):
        return "teams"
    return "matches"


def _special_pages():
    """
    Returns ``(pages, skipped)``: the competition component's routes that no
    model owns, with the arguments of the current season, its competition and
    its next match day, and the routes left out with the reason.
    """
    season = _season()
    if season is None:
        return [], [{"model": "special pages", "reason": "there is no current season"}]
    competition = season.competition
    component = next(
        c
        for __, app_name, __, c, __ in site.get_components()
        if app_name == "competition"
    )

    def named(name, **kwargs):
        return str(component.reverse(name, kwargs=kwargs))

    pages = []
    skipped = []

    def add(name, make):
        try:
            pages.append(_page(name, make(), "special"))
        except NoReverseMatch as exc:
            skipped.append({"model": name, "reason": "does not reverse: %s" % exc})

    def leave_out(name, reason):
        skipped.append({"model": name, "reason": reason})

    base = {"competition_id": competition.pk, "season_id": season.pk}
    day = _next_match_day(season)
    if day is not None:
        dated = dict(base, datestr=day.isoformat())
        add("match-results", lambda: named("match-results", **dated))
        add("match-schedule", lambda: named("match-schedule", **dated))
        add("match-runsheet", lambda: named("match-runsheet", **dated))
        add("match-grid", lambda: named("match-grid", mode="html", **dated))
        add("match-visual-schedule", lambda: named("match-visual-schedule", **dated))
        add("scorecards", lambda: named("scorecards", mode="html", **dated))
        add("match-washout", lambda: named("match-washout", **dated))
        add("match-live-stream", lambda: named("match-live-stream", **dated))
    else:
        leave_out("dated pages", "the season has no match still to play")
    add("scorecard-report", lambda: named("scorecard-report"))

    season_ns = season._get_admin_namespace()
    season_args = season.url_names["edit"].args
    add("report", lambda: _reverse("%s:report" % season_ns, season_args))
    add("summary", lambda: _reverse("%s:summary" % season_ns, season_args))
    add(
        "progression-list",
        lambda: _reverse("%s:progression-list" % season_ns, season_args),
    )
    add("json-builder", lambda: _reverse("%s:json-builder" % season_ns, season_args))
    add("reschedule", lambda: _reverse("%s:reschedule" % season_ns, season_args))
    add(
        "match-grid-season",
        lambda: named("competition:season:match-grid", mode="html", **base),
    )
    if season.upstream_enabled:
        add(
            "upstream-sync",
            lambda: _reverse("%s:upstream-sync" % season_ns, season_args),
        )
    else:
        # Never enabled in the seed: the page names a remote host to fetch from,
        # and opening it as the baseline does would contact that host.
        leave_out(
            "upstream-sync",
            "the season has no upstream, and enabling one would contact a remote host",
        )

    division = pick(Division)
    if division is not None:
        division_ns = division._get_admin_namespace()
        division_args = division.url_names["edit"].args
        add("scorers", lambda: _reverse("%s:scorers" % division_ns, division_args))
        add(
            "bulk-division",
            lambda: _reverse("%s:bulk" % division_ns, division_args[:-1]),
        )
        add(
            "bulk-team",
            lambda: _reverse("%s:bulk" % Team()._get_admin_namespace(), division_args),
        )

    club = Club.objects.filter(teams__division__season=season).order_by("pk").first()
    if club is not None:
        club_ns = club._get_admin_namespace()
        add(
            "officials",
            lambda: _reverse("%s:officials" % club_ns, [club.pk, season.pk]),
        )
        add(
            "registration-form",
            lambda: _reverse(
                "%s:registration-form" % club_ns, [club.pk, season.pk, "html"]
            ),
        )
        person = club.members.order_by("last_name", "first_name", "pk").first()
        if person is not None:
            person_ns = person._get_admin_namespace()
            add(
                "person-merge",
                lambda: _reverse("%s:merge" % person_ns, person.url_names["edit"].args),
            )
        else:
            leave_out("person-merge", "the club has no person to merge")

    stage = pick(Stage)
    if stage is not None:
        add("build", lambda: str(stage.urls["build"]))
    variants = {}
    for candidate in Stage.objects.filter(division__season=season).order_by("pk"):
        variants.setdefault(_progress_variant(candidate), candidate)
    for variant in ("teams", "matches"):
        if variant in variants:
            candidate = variants[variant]
            add("progress-%s" % variant, lambda: str(candidate.urls["progress"]))
        else:
            leave_out(
                "progress-%s" % variant,
                "no stage in the season gives the progress %s page" % variant,
            )

    match = pick(Match)
    if match is not None:
        match_ns = match._get_admin_namespace()
        add("referees", lambda: str(match.urls["referees"]))
        add(
            "detail",
            lambda: _reverse("%s:detail" % match_ns, match.url_names["edit"].args),
        )

    return pages, skipped


def discover() -> dict:
    """
    Every admin page to capture, and the models that have none.

    Needs Django set up and the database seeded.
    """
    pages = _static_pages()
    skipped = []

    for model, name in _models():
        model_pages, reason = _model_pages(model, name)
        if reason is not None:
            skipped.append({"model": model._meta.object_name, "reason": reason})
        pages.extend(model_pages)

    for found, left_out in (_node_pages(), _content_pages(), _special_pages()):
        pages.extend(found)
        skipped.extend(left_out)
    pages.extend(_auth_pages())

    names = Counter(page["name"] for page in pages)
    duplicates = sorted(name for name, count in names.items() if count > 1)
    if duplicates:
        raise ValueError("page names are not unique: %s" % ", ".join(duplicates))
    wrong = [page["url"] for page in pages if not page["url"].startswith("/admin/")]
    if wrong:
        raise ValueError("pages outside /admin/: %s" % ", ".join(wrong))
    return {"pages": pages, "skipped": skipped}


def main(argv: list[str]) -> int:
    """``python -m harness pages [name]``."""
    if argv:
        name = normalise(argv[0])
    else:
        prefix = database_name("x").removesuffix("x")
        db = settings.DATABASES["default"]["NAME"]
        if not db.startswith(prefix):
            print(
                "pages: pass the name, the database is called %s" % db, file=sys.stderr
            )
            return 64
        name = normalise(db[len(prefix) :])

    found = discover()
    target = paths_for(name)["state"]
    target.mkdir(parents=True, exist_ok=True)
    (target / "pages.json").write_text(json.dumps(found, indent=2) + "\n")
    print(
        "%d pages, %d skipped: %s"
        % (len(found["pages"]), len(found["skipped"]), target / "pages.json")
    )
    return 0
