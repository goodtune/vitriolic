"""
The content middleware caches the URL tree of the sitemap, and the
competition sites that nodes mount are part of it. Saving or deleting a
competition, season, club, division or team throws that tree away, so the next
request builds it from the database again.
"""

from contextlib import nullcontext

from django.core.cache import cache
from django.test import override_settings
from test_plus import TestCase

from touchtechnology.admin.tests.tenancy import as_tenant, schema_context
from touchtechnology.content.tests.test_middleware import URLPATTERNS_CACHES
from touchtechnology.content.utils import DEHYDRATED_URLPATTERNS_KEY
from tournamentcontrol.competition.tests import factories


@override_settings(
    CACHES=URLPATTERNS_CACHES, ROOT_URLCONF="tournamentcontrol.competition.tests.urls"
)
class UrlpatternsCacheTests(TestCase):
    """
    A competition, season or division with anything under it cannot be
    deleted, so each test makes only the object it deletes and what is above
    it.
    """

    schema_name = None

    def setUp(self):
        super().setUp()
        self.addCleanup(cache.clear)

    def tenant(self):
        return nullcontext()

    def assertGoneOnTheNextRequest(self, obj, url_name, *args):
        with self.tenant():
            # The visit caches the tree.
            self.get(url_name, *args)
            self.assert_http_200_ok()

            obj.delete()

            self.assertEqual(
                cache.get(DEHYDRATED_URLPATTERNS_KEY, version=self.schema_name), None
            )
            self.get(url_name, *args)

        self.assert_http_404_not_found()

    def test_deleted_competition(self):
        competition = factories.CompetitionFactory.create()

        self.assertGoneOnTheNextRequest(
            competition, "competition:competition", competition.slug
        )

    def test_deleted_season(self):
        season = factories.SeasonFactory.create()

        self.assertGoneOnTheNextRequest(
            season, "competition:season", season.competition.slug, season.slug
        )

    def test_deleted_club(self):
        team = factories.TeamFactory.create()
        season = team.division.season
        season.competition.clubs.add(team.club)

        self.assertGoneOnTheNextRequest(
            team.club,
            "competition:club",
            season.competition.slug,
            season.slug,
            team.club.slug,
        )

    def test_deleted_division(self):
        division = factories.DivisionFactory.create()

        self.assertGoneOnTheNextRequest(
            division,
            "competition:division",
            division.season.competition.slug,
            division.season.slug,
            division.slug,
        )

    def test_deleted_team(self):
        team = factories.TeamFactory.create()

        self.assertGoneOnTheNextRequest(
            team,
            "competition:team",
            team.division.season.competition.slug,
            team.division.season.slug,
            team.division.slug,
            team.slug,
        )


@as_tenant
class TenantUrlpatternsCacheTests(UrlpatternsCacheTests):
    """The same, for a tenant: the tree thrown away is its own."""

    schema_name = "alpha"

    def tenant(self):
        return schema_context(self.schema_name)
