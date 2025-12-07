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
    
    def assertGoodEditView(self, viewname, *args, **kwargs):
        test_query_count = kwargs.pop("test_query_count", 50)
        self.assertLoginRequired(viewname, *args)
        with self.login(self.superuser):
            self.assertGoodView(viewname, test_query_count=test_query_count, *args)
            if kwargs:
                self.post(viewname, *args, **kwargs)
                self.response_302()
    
    def assertGoodDeleteView(self, viewname, *args):
        self.assertLoginRequired(viewname, *args)
        with self.login(self.superuser):
            self.get(viewname, *args)
            self.response_405()
            self.post(viewname, *args)
            self.response_302()
    
    def assertGoodNamespace(self, instance, **kwargs):
        namespace = instance._get_admin_namespace()
        args = instance._get_url_args()
        self.assertGoodEditView("%s:add" % namespace, *args[:-1], **kwargs)
        self.assertGoodEditView("%s:edit" % namespace, *args, **kwargs)
        self.assertGoodDeleteView("%s:delete" % namespace, *args)


class LogoFieldTestCase(TestCase):
    """Test that logo fields accept valid file formats via admin views."""
    
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

    def test_logo_fields_optional(self):
        """Verify logo fields are optional (blank=True, null=True)."""
        competition = CompetitionFactory()
        # ImageField.name is None when no file is uploaded
        self.assertIsNone(competition.logo_colour.name)
        self.assertIsNone(competition.logo_monochrome.name)

    def test_competition_logo_accepts_png(self):
        """Test that Competition accepts PNG files for logos via admin."""
        competition = CompetitionFactory()
        namespace = competition._get_admin_namespace()
        args = competition._get_url_args()
        
        self.assertGoodEditView(
            "%s:edit" % namespace,
            *args,
            data={
                "title": competition.title,
                "slug": competition.slug,
                "logo_colour": SimpleUploadedFile(
                    "competition_logo.png", self.png_data, content_type="image/png"
                )
            }
        )

    def test_club_logo_accepts_jpg(self):
        """Test that Club accepts JPG files for logos via admin."""
        club = ClubFactory()
        namespace = club._get_admin_namespace()
        args = club._get_url_args()
        
        self.assertGoodEditView(
            "%s:edit" % namespace,
            *args,
            data={
                "title": club.title,
                "slug": club.slug,
                "logo_monochrome": SimpleUploadedFile(
                    "club_logo.jpg", self.jpg_data, content_type="image/jpeg"
                )
            }
        )

    def test_season_logo_accepts_svg(self):
        """Test that Season accepts SVG files for logos via admin."""
        season = SeasonFactory()
        namespace = season._get_admin_namespace()
        args = season._get_url_args()
        
        self.assertGoodEditView(
            "%s:edit" % namespace,
            *args,
            data={
                "title": season.title,
                "slug": season.slug,
                "logo_colour": SimpleUploadedFile(
                    "season_logo.svg", self.svg_data, content_type="image/svg+xml"
                )
            }
        )

    def test_division_logo_accepts_png(self):
        """Test that Division accepts PNG files for logos via admin."""
        division = DivisionFactory()
        namespace = division._get_admin_namespace()
        args = division._get_url_args()
        
        self.assertGoodEditView(
            "%s:edit" % namespace,
            *args,
            data={
                "title": division.title,
                "slug": division.slug,
                "logo_colour": SimpleUploadedFile(
                    "division_logo.png", self.png_data, content_type="image/png"
                )
            }
        )

    def test_team_logo_accepts_jpg(self):
        """Test that Team accepts JPG files for logos via admin."""
        team = TeamFactory()
        namespace = team._get_admin_namespace()
        args = team._get_url_args()
        
        self.assertGoodEditView(
            "%s:edit" % namespace,
            *args,
            data={
                "title": team.title,
                "slug": team.slug,
                "logo_monochrome": SimpleUploadedFile(
                    "team_logo.jpg", self.jpg_data, content_type="image/jpeg"
                )
            }
        )

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
