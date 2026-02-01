from django.core.exceptions import ValidationError
from django.db import IntegrityError
from test_plus import TestCase

from tournamentcontrol.competition.models import Division
from tournamentcontrol.competition.tests import factories


class DivisionColorUniquenessTests(TestCase):
    """Test cases for Division color uniqueness constraint within a Season."""

    @classmethod
    def setUpTestData(cls):
        cls.user_factory = factories.SuperUserFactory
        cls.season = factories.SeasonFactory.create()
        cls.division1 = factories.DivisionFactory.create(
            season=cls.season, color="#ff0000"
        )

    def test_different_colors_in_same_season_allowed(self):
        """Test that divisions in the same season can have different colors."""
        division2 = factories.DivisionFactory.create(
            season=self.season, color="#00ff00"
        )
        self.assertEqual(division2.color, "#00ff00")

    def test_same_color_in_different_seasons_allowed(self):
        """Test that divisions in different seasons can have the same color."""
        season2 = factories.SeasonFactory.create()
        division2 = factories.DivisionFactory.create(
            season=season2, color="#ff0000"  # Same color as division1
        )
        self.assertEqual(division2.color, "#ff0000")

    def test_duplicate_color_in_same_season_rejected(self):
        """Test that duplicate colors in the same season are rejected."""
        with self.assertRaises(IntegrityError):
            factories.DivisionFactory.create(
                season=self.season, color="#ff0000"  # Same as division1
            )

    def test_updating_to_duplicate_color_rejected(self):
        """Test that updating a division to a duplicate color is rejected."""
        division2 = factories.DivisionFactory.create(
            season=self.season, color="#00ff00"
        )
        division2.color = "#ff0000"  # Same as division1
        with self.assertRaises(IntegrityError):
            division2.save()

    def test_updating_to_unique_color_allowed(self):
        """Test that updating a division to a unique color is allowed."""
        division2 = factories.DivisionFactory.create(
            season=self.season, color="#00ff00"
        )
        division2.color = "#0000ff"
        division2.save()
        division2.refresh_from_db()
        self.assertEqual(division2.color, "#0000ff")

    def test_updating_same_division_color_allowed(self):
        """Test that updating a division's color to its current value is allowed."""
        self.division1.color = "#ff0000"
        self.division1.save()  # Should not raise
        self.division1.refresh_from_db()
        self.assertEqual(self.division1.color, "#ff0000")


class DivisionColorUpdateViewTests(TestCase):
    """Test cases for the inline division color update endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user_factory = factories.SuperUserFactory
        cls.competition = factories.CompetitionFactory.create()
        cls.season = factories.SeasonFactory.create(competition=cls.competition)
        cls.division1 = factories.DivisionFactory.create(
            season=cls.season, color="#ff0000"
        )
        cls.division2 = factories.DivisionFactory.create(
            season=cls.season, color="#00ff00"
        )

    def setUp(self):
        self.user = self.make_user()
        self.login(self.user)

    def test_update_color_success(self):
        """Test successful color update via HTMX endpoint."""
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        response = self.post(url, data={"color": "#0000ff"})
        self.response_200(response)
        self.assertResponseContains("✓")
        
        self.division1.refresh_from_db()
        self.assertEqual(self.division1.color, "#0000ff")

    def test_update_color_requires_post(self):
        """Test that the endpoint requires POST method."""
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        response = self.get(url)
        self.assertEqual(response.status_code, 405)

    def test_update_color_invalid_format(self):
        """Test that invalid color formats are rejected."""
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        response = self.post(url, data={"color": "red"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid color format", response.content.decode())

    def test_update_color_missing_hash(self):
        """Test that color without # prefix is rejected."""
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        response = self.post(url, data={"color": "ff0000"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid color format", response.content.decode())

    def test_update_color_short_hex(self):
        """Test that short hex codes are rejected."""
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        response = self.post(url, data={"color": "#f00"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid color format", response.content.decode())

    def test_update_color_duplicate_rejected(self):
        """Test that duplicate colors in the same season are rejected."""
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        # Try to update division1 to the same color as division2
        response = self.post(url, data={"color": "#00ff00"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("already used", response.content.decode())

    def test_update_color_same_value_allowed(self):
        """Test that updating to the same color value is allowed."""
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        response = self.post(url, data={"color": "#ff0000"})
        self.response_200(response)
        self.assertResponseContains("✓")

    def test_update_color_unauthorized_access(self):
        """Test that unauthorized users cannot update colors."""
        self.client.logout()
        url = self.reverse(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        response = self.post(url, data={"color": "#0000ff"})
        self.assertEqual(response.status_code, 302)  # Redirect to login


class DivisionListColorWidgetTests(TestCase):
    """Test cases for the division list template with color picker widget."""

    @classmethod
    def setUpTestData(cls):
        cls.user_factory = factories.SuperUserFactory
        cls.competition = factories.CompetitionFactory.create()
        cls.season = factories.SeasonFactory.create(competition=cls.competition)
        cls.division = factories.DivisionFactory.create(
            season=cls.season, color="#ff5733"
        )

    def setUp(self):
        self.user = self.make_user()
        self.login(self.user)

    def test_season_edit_page_displays_color_column(self):
        """Test that the season edit page displays the color column."""
        url = self.reverse(
            "admin:fixja:competition:season:edit",
            self.competition.pk,
            self.season.pk,
        )
        response = self.get(url)
        self.response_200(response)
        # Check that Color header is present
        content = response.content.decode()
        self.assertIn("Color", content)

    def test_division_list_shows_color_picker(self):
        """Test that each division row contains a color picker widget."""
        url = self.reverse(
            "admin:fixja:competition:season:edit",
            self.competition.pk,
            self.season.pk,
        )
        response = self.get(url)
        self.response_200(response)
        content = response.content.decode()
        # Check for color input type
        self.assertIn('type="color"', content)
        # Check that the division's color is set as the value
        self.assertIn(self.division.color, content)

    def test_color_picker_has_htmx_attributes(self):
        """Test that the color picker has HTMX attributes."""
        url = self.reverse(
            "admin:fixja:competition:season:edit",
            self.competition.pk,
            self.season.pk,
        )
        response = self.get(url)
        self.response_200(response)
        content = response.content.decode()
        # Check for HTMX attributes
        self.assertIn("hx-post", content)
        self.assertIn("hx-trigger", content)
        self.assertIn("hx-target", content)
