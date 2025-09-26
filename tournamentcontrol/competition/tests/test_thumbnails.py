"""
Tests for YouTube thumbnail management functionality.
"""

import io
from unittest.mock import patch

from django.test import TestCase
from PIL import Image

from tournamentcontrol.competition._mediaupload import MediaMemoryUpload
from tournamentcontrol.competition.tests.factories import (
    MatchFactory,
    SeasonFactory,
)
from tournamentcontrol.competition.utils import (
    ThumbnailPreview,
    create_thumbnail_preview,
)


class MediaMemoryUploadTestCase(TestCase):
    """Test the MediaMemoryUpload class."""

    def setUp(self):
        self.image_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        self.mimetype = "image/png"

    @patch("magic.from_buffer")
    def test_media_memory_upload_creation(self, mock_magic):
        """Test creating MediaMemoryUpload with binary data."""
        mock_magic.return_value = self.mimetype
        upload = MediaMemoryUpload(self.image_data)

        self.assertEqual(upload.mimetype(), self.mimetype)
        self.assertEqual(upload.size(), len(self.image_data))
        self.assertFalse(upload.resumable())
        self.assertTrue(upload.has_stream())

    @patch("magic.from_buffer")
    def test_media_memory_upload_resumable(self, mock_magic):
        """Test creating resumable MediaMemoryUpload."""
        mock_magic.return_value = self.mimetype
        upload = MediaMemoryUpload(self.image_data, resumable=True)
        self.assertTrue(upload.resumable())

    @patch("magic.from_buffer")
    def test_getbytes(self, mock_magic):
        """Test getting bytes from upload."""
        mock_magic.return_value = self.mimetype
        upload = MediaMemoryUpload(self.image_data)

        # Get first 10 bytes
        chunk = upload.getbytes(0, 10)
        self.assertEqual(chunk, self.image_data[:10])

        # Get middle chunk
        chunk = upload.getbytes(5, 15)
        self.assertEqual(chunk, self.image_data[5:15])

    @patch("magic.from_buffer")
    def test_auto_detect_mimetype(self, mock_magic):
        """Test auto-detecting MIME type when creating MediaMemoryUpload."""
        mock_magic.return_value = "image/png"
        upload = MediaMemoryUpload(self.image_data)

        self.assertIsNotNone(upload)
        self.assertEqual(upload.mimetype(), "image/png")
        mock_magic.assert_called_once_with(self.image_data, mime=True)


class SeasonThumbnailTestCase(TestCase):
    """Test Season thumbnail functionality."""

    def setUp(self):
        self.season = SeasonFactory()
        self.image_data = b"fake image data"
        self.mimetype = "image/jpeg"

    def test_set_thumbnail_image(self):
        """Test setting thumbnail image on season."""
        self.season.live_stream_thumbnail_image = self.image_data
        self.season.save()

        self.season.refresh_from_db()
        self.assertEqual(self.season.live_stream_thumbnail_image, self.image_data)

    @patch("magic.from_buffer")
    def test_get_thumbnail_media_upload(self, mock_magic):
        """Test getting MediaMemoryUpload from season."""
        mock_magic.return_value = self.mimetype

        self.season.live_stream_thumbnail_image = self.image_data
        self.season.save()

        upload = self.season.get_thumbnail_media_upload()

        self.assertIsNotNone(upload)
        self.assertIsInstance(upload, MediaMemoryUpload)
        self.assertEqual(upload.mimetype(), self.mimetype)

    def test_get_thumbnail_media_upload_no_image(self):
        """Test getting MediaMemoryUpload when no image is set."""
        upload = self.season.get_thumbnail_media_upload()

        self.assertIsNone(upload)


class MatchThumbnailTestCase(TestCase):
    """Test Match thumbnail functionality."""

    def setUp(self):
        self.season = SeasonFactory()
        self.match = MatchFactory(stage__division__season=self.season)
        self.image_data = b"fake image data"
        self.mimetype = "image/jpeg"
        self.season_image_data = b"season image data"
        self.season_mimetype = "image/png"

    @patch("magic.from_buffer")
    def test_get_thumbnail_media_upload_match_specific(self, mock_magic):
        """Test getting MediaMemoryUpload from match with its own thumbnail."""
        mock_magic.return_value = self.mimetype

        self.match.live_stream_thumbnail_image = self.image_data
        self.match.save()

        upload = self.match.get_thumbnail_media_upload()

        self.assertIsNotNone(upload)
        self.assertEqual(upload.mimetype(), self.mimetype)
        self.assertEqual(upload.size(), len(self.image_data))

    @patch("magic.from_buffer")
    def test_get_thumbnail_media_upload_fallback_to_season(self, mock_magic):
        """Test getting MediaMemoryUpload falling back to season thumbnail."""
        mock_magic.return_value = self.season_mimetype

        # Set season thumbnail
        self.season.live_stream_thumbnail_image = self.season_image_data
        self.season.save()

        # Match has no thumbnail
        upload = self.match.get_thumbnail_media_upload()

        self.assertIsNotNone(upload)
        self.assertEqual(upload.mimetype(), self.season_mimetype)
        self.assertEqual(upload.size(), len(self.season_image_data))

    def test_get_thumbnail_media_upload_no_thumbnail(self):
        """Test getting MediaMemoryUpload when neither match nor season has thumbnail."""
        upload = self.match.get_thumbnail_media_upload()

        self.assertIsNone(upload)

    @patch("magic.from_buffer")
    def test_match_thumbnail_priority_over_season(self, mock_magic):
        """Test that match thumbnail takes priority over season thumbnail."""

        # Mock magic to return different values based on input
        def mock_magic_side_effect(data, mime=True):
            if data == self.image_data:
                return self.mimetype
            elif data == self.season_image_data:
                return self.season_mimetype
            return "application/octet-stream"

        mock_magic.side_effect = mock_magic_side_effect

        # Set both season and match thumbnails
        self.season.live_stream_thumbnail_image = self.season_image_data
        self.season.save()

        self.match.live_stream_thumbnail_image = self.image_data
        self.match.save()

        upload = self.match.get_thumbnail_media_upload()

        # Should use match thumbnail, not season
        self.assertEqual(upload.mimetype(), self.mimetype)
        self.assertEqual(upload.size(), len(self.image_data))


class ThumbnailPreviewTestCase(TestCase):
    """Test PIL-based thumbnail preview functionality."""

    def setUp(self):
        # Create a small test image
        self.test_image = Image.new("RGB", (100, 100), color="red")
        self.image_buffer = io.BytesIO()
        self.test_image.save(self.image_buffer, format="PNG")
        self.image_data = self.image_buffer.getvalue()

        # Create a large test image
        self.large_image = Image.new("RGB", (2000, 1500), color="blue")
        self.large_buffer = io.BytesIO()
        self.large_image.save(self.large_buffer, format="JPEG")
        self.large_image_data = self.large_buffer.getvalue()

    def test_create_thumbnail_preview_success(self):
        """Test successful creation of thumbnail preview."""
        result = create_thumbnail_preview(self.image_data)

        self.assertIsNotNone(result.image_data)
        self.assertIsInstance(result.image_data, bytes)
        self.assertEqual(result.original_mime_type, "image/png")

        # Test data URL generation
        data_url = result.to_data_url()
        self.assertIsNotNone(data_url)
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))

    def test_create_thumbnail_preview_large_image(self):
        """Test thumbnail preview creation with large image."""
        result = create_thumbnail_preview(
            self.large_image_data, max_width=640, max_height=480
        )

        self.assertIsNotNone(result.image_data)
        self.assertIsInstance(result.image_data, bytes)
        self.assertEqual(result.original_mime_type, "image/jpeg")

        # Test data URL generation
        data_url = result.to_data_url()
        self.assertIsNotNone(data_url)
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))

        # Verify the preview is smaller than original
        self.assertLess(len(result.image_data), len(self.large_image_data))

    def test_create_thumbnail_preview_rgba_conversion(self):
        """Test that RGBA images are properly converted to RGB."""
        rgba_image = Image.new(
            "RGBA", (100, 100), color=(255, 0, 0, 128)
        )  # Semi-transparent red
        rgba_buffer = io.BytesIO()
        rgba_image.save(rgba_buffer, format="PNG")
        rgba_data = rgba_buffer.getvalue()

        result = create_thumbnail_preview(rgba_data)

        self.assertIsNotNone(result.image_data)
        self.assertIsInstance(result.image_data, bytes)
        self.assertEqual(result.original_mime_type, "image/png")

        # Test data URL generation
        data_url = result.to_data_url()
        self.assertIsNotNone(data_url)
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))

    def test_create_thumbnail_preview_custom_quality(self):
        """Test thumbnail creation with custom quality settings."""
        result_high = create_thumbnail_preview(self.image_data, quality=95)
        result_low = create_thumbnail_preview(self.image_data, quality=50)

        self.assertIsNotNone(result_high.image_data)
        self.assertIsNotNone(result_low.image_data)
        self.assertIsInstance(result_high.image_data, bytes)
        self.assertIsInstance(result_low.image_data, bytes)
        # Lower quality should result in smaller file
        self.assertLess(len(result_low.image_data), len(result_high.image_data))

    def test_create_thumbnail_preview_invalid_data(self):
        """Test thumbnail creation with invalid image data."""
        invalid_data = b"not an image"
        result = create_thumbnail_preview(invalid_data)

        self.assertIsNone(result.image_data)
        self.assertIsNone(result.original_mime_type)

        # Test data URL generation with invalid data
        data_url = result.to_data_url()
        self.assertIsNone(data_url)

    def test_create_thumbnail_preview_aspect_ratio_preservation(self):
        """Test that aspect ratio is preserved during thumbnail creation."""
        # Create a wide image (2:1 aspect ratio)
        wide_image = Image.new("RGB", (200, 100), color="green")
        wide_buffer = io.BytesIO()
        wide_image.save(wide_buffer, format="JPEG")
        wide_data = wide_buffer.getvalue()

        result = create_thumbnail_preview(wide_data, max_width=640, max_height=480)

        self.assertIsNotNone(result.image_data)
        self.assertIsInstance(result.image_data, bytes)

        # Test data URL generation
        data_url = result.to_data_url()
        self.assertIsNotNone(data_url)

        # Now we can easily verify the actual dimensions by decoding the image data
        result_image = Image.open(io.BytesIO(result.image_data))
        result_width, result_height = result_image.size

        # Verify aspect ratio is preserved (2:1 ratio)
        aspect_ratio = result_width / result_height
        self.assertAlmostEqual(aspect_ratio, 2.0, places=1)

        # Verify it fits within the specified bounds
        self.assertLessEqual(result_width, 640)
        self.assertLessEqual(result_height, 480)
