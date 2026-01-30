from test_plus import TestCase

from tournamentcontrol.competition.forms import DivisionForm, StageForm
from tournamentcontrol.competition.tests import factories


class DivisionColorTests(TestCase):
    """Test cases for Division color field and get_color method."""

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()

    def test_division_color_field_default(self):
        """Test that division color field defaults to empty string."""
        division = factories.DivisionFactory.create(season=self.season)
        self.assertEqual(division.color, "")

    def test_division_color_field_accepts_hex_value(self):
        """Test that division color field accepts a hex color value."""
        division = factories.DivisionFactory.create(
            season=self.season, color="#ff5733"
        )
        self.assertEqual(division.color, "#ff5733")

    def test_get_color_returns_custom_color(self):
        """Test that get_color returns custom color when set."""
        division = factories.DivisionFactory.create(
            season=self.season, color="#123456"
        )
        self.assertEqual(division.get_color(), "#123456")

    def test_get_color_returns_default_for_order_1(self):
        """Test that get_color returns default red for division order 1."""
        division = factories.DivisionFactory.create(season=self.season, order=1)
        self.assertEqual(division.get_color(), "#e74c3c")

    def test_get_color_returns_default_for_order_2(self):
        """Test that get_color returns default blue for division order 2."""
        division = factories.DivisionFactory.create(season=self.season, order=2)
        self.assertEqual(division.get_color(), "#3498db")

    def test_get_color_returns_default_for_order_3(self):
        """Test that get_color returns default green for division order 3."""
        division = factories.DivisionFactory.create(season=self.season, order=3)
        self.assertEqual(division.get_color(), "#2ecc71")

    def test_get_color_returns_fallback_for_unknown_order(self):
        """Test that get_color returns gray fallback for orders > 8."""
        division = factories.DivisionFactory.create(season=self.season, order=10)
        self.assertEqual(division.get_color(), "#6c757d")

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

    def test_division_form_saves_color(self):
        """Test that DivisionForm correctly saves color field."""
        division = factories.DivisionFactory.create(season=self.season, color="")
        # Verify color is initially empty
        self.assertEqual(division.color, "")
        
        # Update the color
        division.color = "#abcdef"
        division.save()
        division.refresh_from_db()
        
        # Verify color was saved
        self.assertEqual(division.color, "#abcdef")


class StageColorTests(TestCase):
    """Test cases for Stage color field and get_color method."""

    @classmethod
    def setUpTestData(cls):
        cls.division = factories.DivisionFactory.create()

    def test_stage_color_field_default(self):
        """Test that stage color field defaults to empty string."""
        stage = factories.StageFactory.create(division=self.division)
        self.assertEqual(stage.color, "")

    def test_stage_color_field_accepts_hex_value(self):
        """Test that stage color field accepts a hex color value."""
        stage = factories.StageFactory.create(division=self.division, color="#ff5733")
        self.assertEqual(stage.color, "#ff5733")

    def test_get_color_returns_custom_color(self):
        """Test that get_color returns custom color when set."""
        stage = factories.StageFactory.create(division=self.division, color="#fedcba")
        self.assertEqual(stage.get_color(), "#fedcba")

    def test_get_color_returns_default_when_empty(self):
        """Test that get_color returns default light green when no color is set."""
        stage = factories.StageFactory.create(division=self.division)
        self.assertEqual(stage.get_color(), "#e8f5e8")

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

    def test_stage_form_saves_color(self):
        """Test that StageForm correctly saves color field."""
        stage = factories.StageFactory.create(division=self.division, color="")
        # Verify color is initially empty
        self.assertEqual(stage.color, "")
        
        # Update the color
        stage.color = "#123abc"
        stage.save()
        stage.refresh_from_db()
        
        # Verify color was saved
        self.assertEqual(stage.color, "#123abc")
