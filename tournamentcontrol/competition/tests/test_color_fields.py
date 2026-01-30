from test_plus import TestCase

from tournamentcontrol.competition.forms import DivisionForm, StageForm
from tournamentcontrol.competition.models import generate_random_color
from tournamentcontrol.competition.tests import factories


class ColorGenerationTests(TestCase):
    """Test cases for color generation helper function."""

    def test_generate_random_color_format(self):
        """Test that generate_random_color returns a valid hex color."""
        color = generate_random_color()
        self.assertRegex(color, r"^#[0-9a-f]{6}$")

    def test_generate_random_color_brightness(self):
        """Test that generated colors are bright (each component >= 128)."""
        color = generate_random_color()
        # Extract RGB components
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        # Each component should be at least 128 (50% brightness)
        self.assertGreaterEqual(r, 128)
        self.assertGreaterEqual(g, 128)
        self.assertGreaterEqual(b, 128)

    def test_generate_random_color_variability(self):
        """Test that generate_random_color produces different colors."""
        colors = [generate_random_color() for _ in range(10)]
        # With 128^3 possible colors, should have at least 8 unique in 10 generations
        unique_colors = set(colors)
        self.assertGreaterEqual(len(unique_colors), 8)


class DivisionColorTests(TestCase):
    """Test cases for Division color field and get_color method."""

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()

    def test_division_color_field_has_default(self):
        """Test that division color field gets a random color on creation."""
        division = factories.DivisionFactory.create(season=self.season)
        # Color should be set and valid hex format
        self.assertIsNotNone(division.color)
        self.assertRegex(division.color, r"^#[0-9a-f]{6}$")

    def test_division_color_field_accepts_hex_value(self):
        """Test that division color field accepts a hex color value."""
        division = factories.DivisionFactory.create(
            season=self.season, color="#ff5733"
        )
        self.assertEqual(division.color, "#ff5733")

    def test_get_color_returns_stored_color(self):
        """Test that get_color returns the stored color."""
        division = factories.DivisionFactory.create(
            season=self.season, color="#123456"
        )
        self.assertEqual(division.get_color(), "#123456")

    def test_division_form_includes_color_field(self):
        """Test that DivisionForm includes the color field."""
        division = factories.DivisionFactory.create(season=self.season)
        form = DivisionForm(instance=division)
        self.assertIn("color", form.fields)

    def test_division_form_color_widget_type(self):
        """Test that DivisionForm uses color input widget."""
        division = factories.DivisionFactory.create(season=self.season)
        form = DivisionForm(instance=division)
        widget = form.fields["color"].widget
        self.assertEqual(widget.input_type, "color")

    def test_division_color_persists(self):
        """Test that division color field correctly persists changes."""
        division = factories.DivisionFactory.create(season=self.season)
        original_color = division.color
        
        # Update the color
        division.color = "#abcdef"
        division.save()
        division.refresh_from_db()
        
        # Verify color was saved
        self.assertEqual(division.color, "#abcdef")
        self.assertNotEqual(division.color, original_color)


class StageColorTests(TestCase):
    """Test cases for Stage color field and get_color method."""

    @classmethod
    def setUpTestData(cls):
        cls.division = factories.DivisionFactory.create()

    def test_stage_color_field_default(self):
        """Test that stage color field defaults to light green."""
        stage = factories.StageFactory.create(division=self.division)
        self.assertEqual(stage.color, "#e8f5e8")

    def test_stage_color_field_accepts_hex_value(self):
        """Test that stage color field accepts a hex color value."""
        stage = factories.StageFactory.create(division=self.division, color="#ff5733")
        self.assertEqual(stage.color, "#ff5733")

    def test_get_color_returns_stored_color(self):
        """Test that get_color returns the stored color."""
        stage = factories.StageFactory.create(division=self.division, color="#fedcba")
        self.assertEqual(stage.get_color(), "#fedcba")

    def test_stage_form_includes_color_field(self):
        """Test that StageForm includes the color field."""
        stage = factories.StageFactory.create(division=self.division)
        form = StageForm(instance=stage)
        self.assertIn("color", form.fields)

    def test_stage_form_color_widget_type(self):
        """Test that StageForm uses color input widget."""
        stage = factories.StageFactory.create(division=self.division)
        form = StageForm(instance=stage)
        widget = form.fields["color"].widget
        self.assertEqual(widget.input_type, "color")

    def test_stage_color_persists(self):
        """Test that stage color field correctly persists changes."""
        stage = factories.StageFactory.create(division=self.division)
        
        # Update the color
        stage.color = "#123abc"
        stage.save()
        stage.refresh_from_db()
        
        # Verify color was saved
        self.assertEqual(stage.color, "#123abc")

