from test_plus import TestCase

from tournamentcontrol.competition.tests import factories


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
        self.post(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
            data={"color": "#0000ff"}
        )
        self.response_200()
        self.assertResponseContains("✓")
        
        self.division1.refresh_from_db()
        self.assertEqual(self.division1.color, "#0000ff")

    def test_update_color_requires_post(self):
        """Test that the endpoint requires POST method."""
        self.get(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
        )
        self.assertEqual(self.last_response.status_code, 405)

    def test_update_color_invalid_format(self):
        """Test that invalid color formats are rejected."""
        self.post(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
            data={"color": "red"}
        )
        self.assertEqual(self.last_response.status_code, 400)
        self.assertIn("color", self.last_response.content.decode().lower())

    def test_update_color_missing_hash(self):
        """Test that color without # prefix is rejected."""
        self.post(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
            data={"color": "ff0000"}
        )
        self.assertEqual(self.last_response.status_code, 400)
        self.assertIn("color", self.last_response.content.decode().lower())

    def test_update_color_short_hex(self):
        """Test that short hex codes are rejected."""
        self.post(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
            data={"color": "#f00"}
        )
        self.assertEqual(self.last_response.status_code, 400)
        self.assertIn("color", self.last_response.content.decode().lower())

    def test_update_color_duplicate_rejected(self):
        """Test that duplicate colors in the same season are rejected."""
        self.post(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
            data={"color": self.division2.color}
        )
        self.assertEqual(self.last_response.status_code, 400)
        # Check for error message about duplicate color
        content = self.last_response.content.decode()
        self.assertIn("color", content.lower())

    def test_update_color_same_value_allowed(self):
        """Test that updating to the same color value is allowed."""
        self.post(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
            data={"color": self.division1.color}
        )
        self.response_200()
        self.assertResponseContains("✓")

    def test_update_color_unauthorized_access(self):
        """Test that unauthorized users cannot update colors."""
        self.client.logout()
        self.post(
            "admin:fixja:competition:season:division:update-color",
            self.competition.pk,
            self.season.pk,
            self.division1.pk,
            data={"color": "#0000ff"}
        )
        self.response_302()  # Redirect to login


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
        self.get(
            "admin:fixja:competition:season:edit",
            self.competition.pk,
            self.season.pk,
        )
        self.response_200()
        # Check that Color header is present in the divisions tab
        self.assertResponseContains('<th>Color</th>', html=True)

    def test_division_list_shows_color_picker(self):
        """Test that each division row contains a color picker widget."""
        self.get(
            "admin:fixja:competition:season:edit",
            self.competition.pk,
            self.season.pk,
        )
        self.response_200()
        # Check for color input with the division's current color value
        content = self.last_response.content.decode()
        self.assertIn(f'type="color"', content)
        self.assertIn(f'value="{self.division.color}"', content)

    def test_color_picker_has_htmx_attributes(self):
        """Test that the color picker has HTMX attributes."""
        self.get(
            "admin:fixja:competition:season:edit",
            self.competition.pk,
            self.season.pk,
        )
        self.response_200()
        # Check for HTMX attributes on the color input
        content = self.last_response.content.decode()
        self.assertIn('hx-post', content)
        self.assertIn('hx-trigger="change"', content)
        self.assertIn(f'hx-target="#color-status-{self.division.pk}"', content)
