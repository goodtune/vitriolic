"""
Tests for the upstream backend API and the ``UPSTREAM_BACKENDS`` loader.
"""

from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.models import Competition, Division, Match
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.upstream import (
    DEFAULT_UPSTREAM_BACKENDS,
    BaseUpstreamBackend,
    UpstreamURLError,
    get_backend_by_key,
    get_backend_for_identifier,
    get_backend_for_url,
    get_backends,
    load_backend,
)
from tournamentcontrol.competition.upstream.backends.mysideline import (
    MySidelineBackend,
)
from tournamentcontrol.competition.upstream.backends.revolutionise import (
    RevolutioniseBackend,
)
from tournamentcontrol.competition.upstream.types import RemoteCompetition


class ExampleBackend(BaseUpstreamBackend):
    """A third provider, as a deployment might add one."""

    key = "example"
    name = "Example Sport"
    competition_url_example = "https://draws.example.com/club"
    season_url_example = "https://draws.example.com/club/2026"

    def matches(self, url):
        return url.startswith("https://draws.example.com/")

    def parse_competition_url(self, url):
        if not self.matches(url):
            raise UpstreamURLError(url)
        return url.rstrip("/")

    def parse_season_url(self, url, competition_url):
        if not url.startswith(competition_url + "/"):
            raise UpstreamURLError(url)
        return url.rstrip("/")

    def new_client(self, session=None):
        return None

    def fetch_snapshot(self, season, client=None):
        return [RemoteCompetition(id="1", name="Division One")]


class Incomplete(BaseUpstreamBackend):
    key = "incomplete"
    name = "Incomplete"


class BadKey(ExampleBackend):
    key = "Not A Key"


EXAMPLE = "tournamentcontrol.competition.tests.test_upstream_backends.ExampleBackend"


class LoaderTests(TestCase):
    def test_defaults(self):
        self.assertEqual(
            [type(b) for b in get_backends()], [MySidelineBackend, RevolutioniseBackend]
        )
        self.assertEqual(
            DEFAULT_UPSTREAM_BACKENDS,
            (
                "tournamentcontrol.competition.upstream.backends.mysideline.MySidelineBackend",
                "tournamentcontrol.competition.upstream.backends.revolutionise.RevolutioniseBackend",
            ),
        )
        self.assertIs(get_backend_by_key("mysideline"), get_backends()[0])
        with self.assertRaises(KeyError):
            get_backend_by_key("example")

    def test_setting_adds_a_backend(self):
        with override_settings(
            UPSTREAM_BACKENDS=list(DEFAULT_UPSTREAM_BACKENDS) + [EXAMPLE]
        ):
            self.assertEqual(
                [b.key for b in get_backends()],
                ["mysideline", "revolutionise", "example"],
            )
            backend = get_backend_for_url("https://draws.example.com/club")
            self.assertIsInstance(backend, ExampleBackend)
            self.assertEqual(backend.identifier(7), "example:7")
            self.assertIs(get_backend_for_identifier("example:7"), backend)
            self.assertEqual(str(backend), "Example Sport")
            self.assertEqual(repr(backend), "<ExampleBackend: example>")
        # Leaving the override restores the defaults.
        self.assertEqual(get_backend_for_identifier("example:7"), None)
        with self.assertRaises(UpstreamURLError):
            get_backend_for_url("https://draws.example.com/club")

    def test_setting_replaces_the_backends(self):
        with override_settings(UPSTREAM_BACKENDS=[EXAMPLE]):
            self.assertEqual([b.key for b in get_backends()], ["example"])
            with self.assertRaises(UpstreamURLError):
                get_backend_for_url(
                    "https://tfa.mysideline.com.au/competitions/association/1"
                )
        # A single dotted path is accepted too.
        with override_settings(UPSTREAM_BACKENDS=EXAMPLE):
            self.assertEqual([b.key for b in get_backends()], ["example"])

    def test_misconfiguration(self):
        prefix = "tournamentcontrol.competition.tests.test_upstream_backends."
        for paths, message in (
            ([prefix + "Missing"], "could not be imported"),
            ([prefix + "LoaderTests"], "not a BaseUpstreamBackend subclass"),
            ([prefix + "Incomplete"], "cannot be instantiated"),
            ([prefix + "BadKey"], "must be a lower-case identifier"),
            ([EXAMPLE, EXAMPLE], "two backends with the key"),
        ):
            with override_settings(UPSTREAM_BACKENDS=paths):
                with self.assertRaisesMessage(ImproperlyConfigured, message):
                    get_backends()

    def test_load_backend(self):
        self.assertIsInstance(load_backend(EXAMPLE), ExampleBackend)
        with self.assertRaises(ImproperlyConfigured):
            load_backend("nowhere.Nothing")


class BackendApiTests(TestCase):
    def test_identifiers(self):
        backend = ExampleBackend()
        self.assertEqual(backend.identifier("a/b"), "example:a/b")
        self.assertTrue(backend.owns_identifier("example:a/b"))
        self.assertFalse(backend.owns_identifier("examples:1"))
        self.assertFalse(backend.owns_identifier(None))
        self.assertEqual(backend.remote_id("example:a/b"), "a/b")
        with self.assertRaises(ValueError):
            backend.remote_id("mysideline:1")

    def test_abstract_methods_are_required(self):
        with self.assertRaises(TypeError):
            Incomplete()
        self.assertEqual(
            sorted(BaseUpstreamBackend.__abstractmethods__),
            [
                "fetch_snapshot",
                "matches",
                "new_client",
                "parse_competition_url",
                "parse_season_url",
            ],
        )


@override_settings(UPSTREAM_BACKENDS=list(DEFAULT_UPSTREAM_BACKENDS) + [EXAMPLE])
class ThirdBackendTests(TestCase):
    """
    The models, forms and reconciler know nothing of any particular backend:
    a backend added through the setting works end to end.
    """

    def test_models_resolve_the_backend(self):
        competition = factories.CompetitionFactory.create(
            upstream_url="https://draws.example.com/club"
        )
        season = factories.SeasonFactory.create(
            competition=competition, upstream_url="https://draws.example.com/club/2026"
        )
        self.assertIsInstance(competition.upstream_backend, ExampleBackend)
        self.assertIsInstance(season.upstream_backend, ExampleBackend)
        self.assertTrue(season.upstream_enabled)
        division = factories.DivisionFactory.create(
            season=season, upstream_id="example:1"
        )
        self.assertIsInstance(division.upstream_backend, ExampleBackend)
        self.assertEqual(Division.objects.get(upstream_id="example:1"), division)

    def test_forms_validate_through_the_backend(self):
        from tournamentcontrol.competition.forms import CompetitionForm, SeasonForm

        superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)
        competition = factories.CompetitionFactory.create()
        form = CompetitionForm(
            data={
                "title": competition.title,
                "slug": competition.slug,
                "upstream_url": "https://draws.example.com/club/",
            },
            instance=competition,
            user=superuser,
        )
        self.assertEqual(form.errors.get("upstream_url"), None)
        self.assertEqual(
            form.cleaned_data["upstream_url"], "https://draws.example.com/club"
        )
        competition.upstream_url = "https://draws.example.com/club"
        competition.save()
        season = factories.SeasonFactory.create(competition=competition)
        form = SeasonForm(
            data={
                "title": season.title,
                "slug": season.slug,
                "mode": season.mode,
                "live_stream_privacy": "public",
                "upstream_url": "https://draws.example.com/club/2026/",
            },
            instance=season,
            user=superuser,
        )
        self.assertEqual(form.errors, {})
        self.assertEqual(
            form.cleaned_data["upstream_url"], "https://draws.example.com/club/2026"
        )

    def test_reconciler_uses_the_backend(self):
        from tournamentcontrol.competition.upstream.sync import synchronise_season

        season = factories.SeasonFactory.create(
            competition__upstream_url="https://draws.example.com/club",
            upstream_url="https://draws.example.com/club/2026",
        )
        result = synchronise_season(season)
        self.assertEqual(result.created, {"division": 1, "stage": 1})
        division = season.divisions.get()
        self.assertEqual(division.upstream_id, "example:1")
        self.assertEqual(division.title, "Division One")
        self.assertEqual(
            Competition.objects.get(pk=season.competition_id).upstream_backend.key,
            "example",
        )
        self.assertEqual(Match.objects.count(), 0)
