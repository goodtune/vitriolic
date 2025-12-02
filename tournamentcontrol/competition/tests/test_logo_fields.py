"""
Tests for logo field validation on Competition, Club, Season, Division, and Team models.
"""

import io
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from test_plus import TestCase as TestPlusTestCase

from tournamentcontrol.competition.models import (
    Club,
    Competition,
    Division,
    Season,
    Team,
)
from tournamentcontrol.competition.tests.factories import (
    ClubFactory,
    CompetitionFactory,
    DivisionFactory,
    SeasonFactory,
    TeamFactory,
)
from tournamentcontrol.competition.validators import validate_logo_aspect_ratio


class LogoFieldTestCase(TestPlusTestCase):
    """Test that logo fields exist and accept valid file formats."""

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
        self.assertIsNone(competition.logo_colour.name or None)
        self.assertIsNone(competition.logo_monochrome.name or None)

    def test_logo_accepts_png(self):
        """Verify logo fields accept PNG files."""
        try:
            from PIL import Image
            
            # Create a simple PNG image in memory
            img = Image.new("RGB", (100, 100), color="red")
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            
            png_file = SimpleUploadedFile(
                "test_logo.png", img_bytes.read(), content_type="image/png"
            )
            
            competition = CompetitionFactory(logo_colour=png_file)
            competition.full_clean()
            self.assertTrue(competition.logo_colour.name.endswith(".png"))
        except ImportError:
            self.skipTest("PIL/Pillow not available")

    def test_logo_accepts_jpg(self):
        """Verify logo fields accept JPG files."""
        try:
            from PIL import Image
            
            # Create a simple JPEG image in memory
            img = Image.new("RGB", (100, 100), color="blue")
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="JPEG")
            img_bytes.seek(0)
            
            jpg_file = SimpleUploadedFile(
                "test_logo.jpg", img_bytes.read(), content_type="image/jpeg"
            )
            
            club = ClubFactory(logo_monochrome=jpg_file)
            club.full_clean()
            self.assertTrue(club.logo_monochrome.name.endswith(".jpg"))
        except ImportError:
            self.skipTest("PIL/Pillow not available")

    def test_logo_rejects_invalid_extension(self):
        """Verify logo fields reject files with invalid extensions."""
        txt_file = SimpleUploadedFile(
            "test_logo.txt", b"This is not an image", content_type="text/plain"
        )
        
        competition = CompetitionFactory(logo_colour=txt_file)
        with self.assertRaises(ValidationError) as cm:
            competition.full_clean()
        
        self.assertIn("logo_colour", cm.exception.error_dict)


class LogoAspectRatioValidatorTestCase(TestCase):
    """Test the aspect ratio validator for logo images."""

    def test_validator_accepts_square_images(self):
        """Verify validator accepts square images (1:1 aspect ratio)."""
        try:
            from PIL import Image
            
            # Create a square image
            img = Image.new("RGB", (100, 100), color="green")
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            
            # Should not raise ValidationError
            validate_logo_aspect_ratio(img_bytes)
        except ImportError:
            self.skipTest("PIL/Pillow not available")

    def test_validator_rejects_non_square_images(self):
        """Verify validator rejects non-square images."""
        try:
            from PIL import Image
            
            # Create a non-square image (2:1 aspect ratio)
            img = Image.new("RGB", (200, 100), color="yellow")
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            
            with self.assertRaises(ValidationError) as cm:
                validate_logo_aspect_ratio(img_bytes)
            
            self.assertEqual(cm.exception.code, "invalid_aspect_ratio")
        except ImportError:
            self.skipTest("PIL/Pillow not available")

    def test_validator_accepts_nearly_square_images(self):
        """Verify validator accepts images within tolerance (10%)."""
        try:
            from PIL import Image
            
            # Create a nearly square image (108x100 = 1.08:1, within 10% tolerance)
            img = Image.new("RGB", (108, 100), color="purple")
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            
            # Should not raise ValidationError (within default 10% tolerance)
            validate_logo_aspect_ratio(img_bytes)
        except ImportError:
            self.skipTest("PIL/Pillow not available")

