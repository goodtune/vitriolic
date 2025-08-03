"""
Tests for YouTube thumbnail management functionality.
"""

import io
from unittest.mock import Mock, patch

from django.test import TestCase

from tournamentcontrol.competition.media import MediaDatabaseUpload
from tournamentcontrol.competition.models import Season, Match
from tournamentcontrol.competition.thumbnail_utils import load_image_from_file
from tournamentcontrol.competition.tests.factories import SeasonFactory, MatchFactory


class MediaDatabaseUploadTestCase(TestCase):
    """Test the MediaDatabaseUpload class."""
    
    def setUp(self):
        self.image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
        self.mimetype = 'image/png'
    
    def test_media_database_upload_creation(self):
        """Test creating MediaDatabaseUpload with binary data."""
        upload = MediaDatabaseUpload(self.image_data, self.mimetype)
        
        self.assertEqual(upload.mimetype(), self.mimetype)
        self.assertEqual(upload.size(), len(self.image_data))
        self.assertFalse(upload.resumable())
        self.assertTrue(upload.has_stream())
    
    def test_media_database_upload_resumable(self):
        """Test creating resumable MediaDatabaseUpload."""
        upload = MediaDatabaseUpload(self.image_data, self.mimetype, resumable=True)
        self.assertTrue(upload.resumable())
    
    def test_getbytes(self):
        """Test getting bytes from upload."""
        upload = MediaDatabaseUpload(self.image_data, self.mimetype)
        
        # Get first 10 bytes
        chunk = upload.getbytes(0, 10)
        self.assertEqual(chunk, self.image_data[:10])
        
        # Get middle chunk
        chunk = upload.getbytes(5, 15)
        self.assertEqual(chunk, self.image_data[5:15])
    
    def test_from_model_field_with_data(self):
        """Test creating MediaDatabaseUpload from model fields."""
        season = SeasonFactory()
        season.thumbnail_image = self.image_data
        season.thumbnail_image_mimetype = self.mimetype
        season.save()
        
        upload = MediaDatabaseUpload.from_model_field(season)
        
        self.assertIsNotNone(upload)
        self.assertEqual(upload.mimetype(), self.mimetype)
        self.assertEqual(upload.size(), len(self.image_data))
    
    def test_from_model_field_no_data(self):
        """Test creating MediaDatabaseUpload from model with no image data."""
        season = SeasonFactory()
        
        upload = MediaDatabaseUpload.from_model_field(season)
        
        self.assertIsNone(upload)
    
    def test_from_model_field_no_mimetype(self):
        """Test error when image data exists but no MIME type."""
        season = SeasonFactory()
        season.thumbnail_image = self.image_data
        # Don't set mimetype
        season.save()
        
        with self.assertRaises(ValueError):
            MediaDatabaseUpload.from_model_field(season)


class SeasonThumbnailTestCase(TestCase):
    """Test Season thumbnail functionality."""
    
    def setUp(self):
        self.season = SeasonFactory()
        self.image_data = b'fake image data'
        self.mimetype = 'image/jpeg'
    
    def test_set_thumbnail_image(self):
        """Test setting thumbnail image on season."""
        self.season.set_thumbnail_image(self.image_data, self.mimetype)
        
        self.season.refresh_from_db()
        self.assertEqual(self.season.thumbnail_image, self.image_data)
        self.assertEqual(self.season.thumbnail_image_mimetype, self.mimetype)
    
    @patch('tournamentcontrol.competition.models.Season.propagate_thumbnail_to_matches')
    def test_set_thumbnail_image_with_propagation(self, mock_propagate):
        """Test setting thumbnail image with propagation."""
        self.season.set_thumbnail_image(self.image_data, self.mimetype, propagate_to_matches=True)
        
        mock_propagate.assert_called_once()
    
    @patch('tournamentcontrol.competition.models.Season.propagate_thumbnail_to_matches')
    def test_set_thumbnail_image_without_propagation(self, mock_propagate):
        """Test setting thumbnail image without propagation."""
        self.season.set_thumbnail_image(self.image_data, self.mimetype, propagate_to_matches=False)
        
        mock_propagate.assert_not_called()
    
    def test_get_thumbnail_media_upload(self):
        """Test getting MediaDatabaseUpload from season."""
        self.season.thumbnail_image = self.image_data
        self.season.thumbnail_image_mimetype = self.mimetype
        self.season.save()
        
        upload = self.season.get_thumbnail_media_upload()
        
        self.assertIsNotNone(upload)
        self.assertIsInstance(upload, MediaDatabaseUpload)
        self.assertEqual(upload.mimetype(), self.mimetype)
    
    def test_get_thumbnail_media_upload_no_image(self):
        """Test getting MediaDatabaseUpload when no image is set."""
        upload = self.season.get_thumbnail_media_upload()
        
        self.assertIsNone(upload)


class MatchThumbnailTestCase(TestCase):
    """Test Match thumbnail functionality."""
    
    def setUp(self):
        self.season = SeasonFactory()
        self.match = MatchFactory(stage__division__season=self.season)
        self.image_data = b'fake image data'
        self.mimetype = 'image/jpeg'
        self.season_image_data = b'season image data'
        self.season_mimetype = 'image/png'
    
    def test_set_thumbnail_image(self):
        """Test setting thumbnail image on match."""
        self.match.set_thumbnail_image(self.image_data, self.mimetype)
        
        self.match.refresh_from_db()
        self.assertEqual(self.match.thumbnail_image, self.image_data)
        self.assertEqual(self.match.thumbnail_image_mimetype, self.mimetype)
    
    def test_has_custom_thumbnail(self):
        """Test checking if match has custom thumbnail."""
        # No thumbnail initially
        self.assertFalse(self.match.has_custom_thumbnail())
        
        # Set thumbnail
        self.match.set_thumbnail_image(self.image_data, self.mimetype)
        self.assertTrue(self.match.has_custom_thumbnail())
    
    def test_get_thumbnail_media_upload_match_specific(self):
        """Test getting MediaDatabaseUpload from match with its own thumbnail."""
        self.match.thumbnail_image = self.image_data
        self.match.thumbnail_image_mimetype = self.mimetype
        self.match.save()
        
        upload = self.match.get_thumbnail_media_upload()
        
        self.assertIsNotNone(upload)
        self.assertEqual(upload.mimetype(), self.mimetype)
        self.assertEqual(upload.size(), len(self.image_data))
    
    def test_get_thumbnail_media_upload_fallback_to_season(self):
        """Test getting MediaDatabaseUpload falling back to season thumbnail."""
        # Set season thumbnail
        self.season.thumbnail_image = self.season_image_data
        self.season.thumbnail_image_mimetype = self.season_mimetype
        self.season.save()
        
        # Match has no thumbnail
        upload = self.match.get_thumbnail_media_upload()
        
        self.assertIsNotNone(upload)
        self.assertEqual(upload.mimetype(), self.season_mimetype)
        self.assertEqual(upload.size(), len(self.season_image_data))
    
    def test_get_thumbnail_media_upload_no_thumbnail(self):
        """Test getting MediaDatabaseUpload when neither match nor season has thumbnail."""
        upload = self.match.get_thumbnail_media_upload()
        
        self.assertIsNone(upload)
    
    def test_match_thumbnail_priority_over_season(self):
        """Test that match thumbnail takes priority over season thumbnail."""
        # Set both season and match thumbnails
        self.season.thumbnail_image = self.season_image_data
        self.season.thumbnail_image_mimetype = self.season_mimetype
        self.season.save()
        
        self.match.thumbnail_image = self.image_data
        self.match.thumbnail_image_mimetype = self.mimetype
        self.match.save()
        
        upload = self.match.get_thumbnail_media_upload()
        
        # Should use match thumbnail, not season
        self.assertEqual(upload.mimetype(), self.mimetype)
        self.assertEqual(upload.size(), len(self.image_data))


class ThumbnailPropagationTestCase(TestCase):
    """Test thumbnail propagation from season to matches."""
    
    def setUp(self):
        self.season = SeasonFactory()
        self.match1 = MatchFactory(stage__division__season=self.season, videos=['https://youtube.com/watch?v=123'])
        self.match2 = MatchFactory(stage__division__season=self.season, videos=['https://youtube.com/watch?v=456'])
        self.match3 = MatchFactory(stage__division__season=self.season)  # No videos
        
        self.image_data = b'season image data'
        self.mimetype = 'image/jpeg'
    
    def test_propagate_thumbnail_to_matches(self):
        """Test propagating season thumbnail to matches."""
        self.season.thumbnail_image = self.image_data
        self.season.thumbnail_image_mimetype = self.mimetype
        self.season.save()
        
        self.season.propagate_thumbnail_to_matches()
        
        # Matches with videos should get the thumbnail
        self.match1.refresh_from_db()
        self.match2.refresh_from_db()
        self.match3.refresh_from_db()
        
        self.assertEqual(self.match1.thumbnail_image, self.image_data)
        self.assertEqual(self.match2.thumbnail_image, self.image_data)
        # Match without videos should not get thumbnail
        self.assertIsNone(self.match3.thumbnail_image)
    
    def test_propagate_does_not_override_custom_thumbnails(self):
        """Test that propagation doesn't override existing match thumbnails."""
        # Set season thumbnail
        self.season.thumbnail_image = self.image_data
        self.season.thumbnail_image_mimetype = self.mimetype
        self.season.save()
        
        # Set custom thumbnail on match1
        custom_data = b'custom image data'
        self.match1.thumbnail_image = custom_data
        self.match1.thumbnail_image_mimetype = 'image/png'
        self.match1.save()
        
        self.season.propagate_thumbnail_to_matches()
        
        # match1 should keep its custom thumbnail
        self.match1.refresh_from_db()
        self.match2.refresh_from_db()
        
        self.assertEqual(self.match1.thumbnail_image, custom_data)  # Unchanged
        self.assertEqual(self.match2.thumbnail_image, self.image_data)  # Updated