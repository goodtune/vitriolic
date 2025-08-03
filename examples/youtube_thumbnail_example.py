#!/usr/bin/env os.path.dirname(os.path.dirname(__file__))
"""
Example script demonstrating YouTube thumbnail management functionality.

This script shows how to use the new database-stored thumbnail system
instead of the old URL-based approach.
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.vitriolic.settings')
django.setup()

from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.thumbnail_utils import (
    set_season_thumbnail_from_file,
    set_youtube_thumbnail_for_video,
)


def main():
    """Example usage of the new thumbnail system."""
    
    # Example for https://youtu.be/MpSsc171CBQ
    season = Season.objects.get(pk=48)
    
    # Method 1: Set season thumbnail from file and propagate to all matches
    print("Setting season thumbnail from file...")
    set_season_thumbnail_from_file(
        season, 
        "AYTC Live Stream Card.jpg", 
        propagate=True
    )
    print(f"Season {season} thumbnail set and propagated to matches")
    
    # Method 2: Directly set thumbnail for a specific video
    print("Setting thumbnail for specific video...")
    result = set_youtube_thumbnail_for_video(
        "MpSsc171CBQ", 
        season, 
        "AYTC Live Stream Card.jpg"
    )
    print(f"YouTube API response: {result}")
    
    # Method 3: Use the new MediaDatabaseUpload class directly (mimics original example)
    print("Using MediaDatabaseUpload directly...")
    from tournamentcontrol.competition.media import MediaDatabaseUpload
    from tournamentcontrol.competition.thumbnail_utils import load_image_from_file
    
    # Load image and store in season
    image_data, mimetype = load_image_from_file("AYTC Live Stream Card.jpg")
    season.set_thumbnail_image(image_data, mimetype, propagate_to_matches=True)
    
    # Create MediaDatabaseUpload instance (equivalent to MediaFileUpload)
    media_body = MediaDatabaseUpload.from_model_field(season, resumable=True)
    
    # Use with YouTube API (equivalent to original example)
    request = season.youtube.thumbnails().set(
        videoId="MpSsc171CBQ",
        media_body=media_body,  # Now sources from database instead of file
    )
    result = request.execute()
    print(f"Direct API call result: {result}")
    
    # Method 4: Working with match-specific thumbnails
    print("Setting match-specific thumbnail...")
    matches = season.matches.filter(videos__isnull=False).exclude(videos=[])
    if matches.exists():
        match = matches.first()
        
        # Set custom thumbnail for this match
        from tournamentcontrol.competition.thumbnail_utils import set_match_thumbnail_from_file
        set_match_thumbnail_from_file(match, "match_specific_thumbnail.jpg")
        
        # This match now has a custom thumbnail and won't be overwritten
        # when season thumbnails are propagated
        print(f"Match {match} now has custom thumbnail: {match.has_custom_thumbnail()}")
        
        # Get the thumbnail for YouTube API
        media_body = match.get_thumbnail_media_upload()  # Returns match-specific thumbnail
        print(f"Match thumbnail media ready: {media_body is not None}")


if __name__ == "__main__":
    main()