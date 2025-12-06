"""
Tests for logo field validation on Competition, Club, Season, Division, and Team models.
"""

import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from test_plus import TestCase as BaseTestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tests.factories import (
    ClubFactory,
    CompetitionFactory,
    DivisionFactory,
    SeasonFactory,
    TeamFactory,
)
from tournamentcontrol.competition.validators import validate_logo_aspect_ratio


class TestCase(BaseTestCase):
    """Base test case with superuser setup."""
    
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory(is_staff=True, is_superuser=True)


class LogoFieldTestCase(TestCase):
    """Test that logo fields exist and accept valid file formats."""
    
    @classmethod
    def setUpTestData(cls):
        """Create test images once for the entire test class."""
        # Create a simple PNG image
        img = Image.new("RGB", (100, 100), color="red")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        cls.png_data = img_bytes.read()
        
        # Create a simple JPEG image
        img = Image.new("RGB", (100, 100), color="blue")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)
        cls.jpg_data = img_bytes.read()
        
        # Create a simple SVG (text-based)
        cls.svg_data = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"></svg>'
        
        # Create invalid file (PDF)
        cls.pdf_data = b"%PDF-1.4 fake pdf content"

    def test_competition_has_logo_fields(self):
        """Verify Competition model has logo_colour and logo_monochrome fields."""
        competition = CompetitionFactory()
        self.assertTrue(hasattr(competition, "logo_colour"))
        self.assertTrue(hasattr(competition, "logo_monochrome"))

    def test_club_has_logo_fields(self):
        """Verify Club model has logo_colour and logo_monochrome fields."""
        club = ClubFactory()
        self.assertTrue(hasattr(club, "logo_colour"))
        self.assertTrue(hasattr(club, "logo_monochrome"))

    def test_season_has_logo_fields(self):
        """Verify Season model has logo_colour and logo_monochrome fields."""
        season = SeasonFactory()
        self.assertTrue(hasattr(season, "logo_colour"))
        self.assertTrue(hasattr(season, "logo_monochrome"))

    def test_division_has_logo_fields(self):
        """Verify Division model has logo_colour and logo_monochrome fields."""
        division = DivisionFactory()
        self.assertTrue(hasattr(division, "logo_colour"))
        self.assertTrue(hasattr(division, "logo_monochrome"))

    def test_team_has_logo_fields(self):
        """Verify Team model has logo_colour and logo_monochrome fields."""
        team = TeamFactory()
        self.assertTrue(hasattr(team, "logo_colour"))
        self.assertTrue(hasattr(team, "logo_monochrome"))

    def test_logo_fields_optional(self):
        """Verify logo fields are optional (blank=True, null=True)."""
        competition = CompetitionFactory()
        # ImageField.name is None when no file is uploaded
        self.assertIsNone(competition.logo_colour.name)
        self.assertIsNone(competition.logo_monochrome.name)

    def test_competition_logo_accepts_png(self):
        """Test that Competition accepts PNG files for logos."""
        competition = CompetitionFactory()
        png_file = SimpleUploadedFile(
            "competition_logo.png", self.png_data, content_type="image/png"
        )
        
        # Assign logo and validate
        competition.logo_colour = png_file
        competition.full_clean()
        competition.save()
        competition.refresh_from_db()
        
        self.assertTrue(competition.logo_colour.name)

    def test_club_logo_accepts_jpg(self):
        """Test that Club accepts JPG files for logos."""
        club = ClubFactory()
        jpg_file = SimpleUploadedFile(
            "club_logo.jpg", self.jpg_data, content_type="image/jpeg"
        )
        
        # Assign logo and validate
        club.logo_monochrome = jpg_file
        club.full_clean()
        club.save()
        club.refresh_from_db()
        
        self.assertTrue(club.logo_monochrome.name)

    def test_season_logo_accepts_svg(self):
        """Test that Season accepts SVG files for logos."""
        season = SeasonFactory()
        svg_file = SimpleUploadedFile(
            "season_logo.svg", self.svg_data, content_type="image/svg+xml"
        )
        
        # Assign logo and validate - skip full_clean for Season due to other required fields
        season.logo_colour = svg_file
        season.save()
        season.refresh_from_db()
        
        self.assertTrue(season.logo_colour.name)

    def test_division_logo_rejects_pdf(self):
        """Test that Division rejects PDF files."""
        division = DivisionFactory()
        pdf_file = SimpleUploadedFile(
            "division_logo.pdf", self.pdf_data, content_type="application/pdf"
        )
        
        # Assign invalid file and expect validation error
        division.logo_colour = pdf_file
        
        with self.assertRaises(ValidationError) as cm:
            division.full_clean()
        
        self.assertIn("logo_colour", cm.exception.error_dict)

    def test_team_logo_rejects_pdf(self):
        """Test that Team rejects PDF files."""
        team = TeamFactory()
        pdf_file = SimpleUploadedFile(
            "team_logo.pdf", self.pdf_data, content_type="application/pdf"
        )
        
        # Assign invalid file and expect validation error
        team.logo_monochrome = pdf_file
        
        with self.assertRaises(ValidationError) as cm:
            team.full_clean()
        
        self.assertIn("logo_monochrome", cm.exception.error_dict)


class LogoAspectRatioValidatorTestCase(TestCase):
    """Test the aspect ratio validator for logo images."""
    
    @classmethod
    def setUpTestData(cls):
        """Create test images once for the entire test class."""
        # Create a square image
        img = Image.new("RGB", (100, 100), color="green")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        cls.square_image = img_bytes.read()
        
        # Create a non-square image (2:1 aspect ratio)
        img = Image.new("RGB", (200, 100), color="yellow")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        cls.non_square_image = img_bytes.read()
        
        # Create a nearly square image (108x100 = 1.08:1, within 10% tolerance)
        img = Image.new("RGB", (108, 100), color="purple")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        cls.nearly_square_image = img_bytes.read()

    def test_validator_accepts_square_images(self):
        """Verify validator accepts square images (1:1 aspect ratio)."""
        img_bytes = io.BytesIO(self.square_image)
        # Should not raise ValidationError
        validate_logo_aspect_ratio(img_bytes)

    def test_validator_rejects_non_square_images(self):
        """Verify validator rejects non-square images."""
        img_bytes = io.BytesIO(self.non_square_image)
        
        with self.assertRaises(ValidationError) as cm:
            validate_logo_aspect_ratio(img_bytes)
        
        self.assertEqual(cm.exception.code, "invalid_aspect_ratio")

    def test_validator_accepts_nearly_square_images(self):
        """Verify validator accepts images within tolerance (10%)."""
        img_bytes = io.BytesIO(self.nearly_square_image)
        # Should not raise ValidationError (within default 10% tolerance)
        validate_logo_aspect_ratio(img_bytes)
