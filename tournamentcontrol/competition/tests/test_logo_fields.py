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
        """Create test data once for the entire test class."""
        # Create a single team which will cascade create division, season, competition, and club
        cls.team = TeamFactory()
        cls.division = cls.team.division
        cls.season = cls.division.season
        cls.competition = cls.season.competition
        cls.club = cls.team.club
        
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
        # ImageField.name is None when no file is uploaded
        self.assertIsNone(self.competition.logo_colour.name)
        self.assertIsNone(self.competition.logo_monochrome.name)

    def test_competition_logo_via_admin(self):
        """Test that Competition edit view includes logo fields."""
        namespace = self.competition._get_admin_namespace()
        args = self.competition._get_url_args()
        
        with self.login(self.superuser):
            response = self.get(f"{namespace}:edit", *args)
            self.response_200()
            self.assertContains(response, "logo_colour")
            self.assertContains(response, "logo_monochrome")

    def test_club_logo_via_admin(self):
        """Test that Club edit view includes logo fields."""
        namespace = self.club._get_admin_namespace()
        args = self.club._get_url_args()
        
        with self.login(self.superuser):
            response = self.get(f"{namespace}:edit", *args)
            self.response_200()
            self.assertContains(response, "logo_colour")
            self.assertContains(response, "logo_monochrome")

    def test_season_logo_via_admin(self):
        """Test that Season edit view includes logo fields."""
        namespace = self.season._get_admin_namespace()
        args = self.season._get_url_args()
        
        with self.login(self.superuser):
            response = self.get(f"{namespace}:edit", *args)
            self.response_200()
            self.assertContains(response, "logo_colour")
            self.assertContains(response, "logo_monochrome")

    def test_division_logo_via_admin(self):
        """Test that Division edit view includes logo fields."""
        namespace = self.division._get_admin_namespace()
        args = self.division._get_url_args()
        
        with self.login(self.superuser):
            response = self.get(f"{namespace}:edit", *args)
            self.response_200()
            self.assertContains(response, "logo_colour")
            self.assertContains(response, "logo_monochrome")

    def test_team_logo_via_admin(self):
        """Test that Team edit view includes logo fields."""
        namespace = self.team._get_admin_namespace()
        args = self.team._get_url_args()
        
        with self.login(self.superuser):
            response = self.get(f"{namespace}:edit", *args)
            self.response_200()
            self.assertContains(response, "logo_colour")
            self.assertContains(response, "logo_monochrome")

    def test_division_logo_rejects_pdf(self):
        """Test that Division rejects PDF files via admin POST."""
        namespace = self.division._get_admin_namespace()
        args = self.division._get_url_args()
        pdf_file = SimpleUploadedFile(
            "division_logo.pdf", self.pdf_data, content_type="application/pdf"
        )
        
        with self.login(self.superuser):
            # POST with invalid file type
            self.post(
                f"{namespace}:edit",
                *args,
                data={
                    "title": self.division.title,
                    "slug": self.division.slug,
                    "logo_colour": pdf_file,
                }
            )
            # Should return 200 with form errors, not 302 redirect
            self.response_200()

    def test_team_logo_rejects_pdf(self):
        """Test that Team rejects PDF files via admin POST."""
        namespace = self.team._get_admin_namespace()
        args = self.team._get_url_args()
        pdf_file = SimpleUploadedFile(
            "team_logo.pdf", self.pdf_data, content_type="application/pdf"
        )
        
        with self.login(self.superuser):
            # POST with invalid file type
            self.post(
                f"{namespace}:edit",
                *args,
                data={
                    "title": self.team.title,
                    "slug": self.team.slug,
                    "logo_monochrome": pdf_file,
                }
            )
            # Should return 200 with form errors, not 302 redirect
            self.response_200()


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
