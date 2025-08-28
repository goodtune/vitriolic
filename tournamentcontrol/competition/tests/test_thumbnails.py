"""
Tests for YouTube thumbnail management functionality.
"""

from unittest.mock import patch

from django.test import TestCase

from tournamentcontrol.competition._mediaupload import MediaMemoryUpload
from tournamentcontrol.competition.tests.factories import SeasonFactory, MatchFactory


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
