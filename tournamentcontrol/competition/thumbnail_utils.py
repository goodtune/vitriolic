"""
Utility functions for working with YouTube thumbnail images.

This module provides convenience functions for loading images from files
and setting them on Season and Match models, as well as functions for
managing thumbnail propagation.
"""

import mimetypes
from pathlib import Path
from typing import Optional


def load_image_from_file(file_path: str) -> tuple[bytes, str]:
    """
    Load image data and MIME type from a file path.
    
    Args:
        file_path: Path to the image file
        
    Returns:
        Tuple of (image_data, mimetype)
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If MIME type cannot be determined
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {file_path}")
    
    # Read the image data
    with open(path, 'rb') as f:
        image_data = f.read()
    
    # Determine MIME type
    mimetype, _ = mimetypes.guess_type(file_path)
    if not mimetype or not mimetype.startswith('image/'):
        raise ValueError(f"Could not determine image MIME type for: {file_path}")
    
    return image_data, mimetype


def set_season_thumbnail_from_file(season, file_path: str, propagate: bool = True):
    """
    Set a season's thumbnail from an image file.
    
    Args:
        season: Season model instance
        file_path: Path to the image file
        propagate: Whether to propagate to matches
    """
    image_data, mimetype = load_image_from_file(file_path)
    season.set_thumbnail_image(image_data, mimetype, propagate_to_matches=propagate)


def set_match_thumbnail_from_file(match, file_path: str):
    """
    Set a match's thumbnail from an image file.
    
    Args:
        match: Match model instance
        file_path: Path to the image file
    """
    image_data, mimetype = load_image_from_file(file_path)
    match.set_thumbnail_image(image_data, mimetype)


def set_youtube_thumbnail_for_video(video_id: str, season, image_path: Optional[str] = None):
    """
    Set YouTube thumbnail for a specific video using the YouTube API.
    
    This is a convenience function that mimics the example in the issue description.
    
    Args:
        video_id: YouTube video ID
        season: Season model instance with YouTube API credentials
        image_path: Optional path to image file. If not provided, uses season's stored thumbnail.
        
    Example:
        # Using stored thumbnail
        set_youtube_thumbnail_for_video("MpSsc171CBQ", season)
        
        # Using file
        set_youtube_thumbnail_for_video("MpSsc171CBQ", season, "AYTC Live Stream Card.jpg")
    """
    from .media import MediaDatabaseUpload
    
    if image_path:
        # Load from file
        image_data, mimetype = load_image_from_file(image_path)
        media_body = MediaDatabaseUpload(image_data, mimetype, resumable=True)
    else:
        # Use season's stored thumbnail
        media_body = season.get_thumbnail_media_upload()
        if not media_body:
            raise ValueError("No thumbnail available - either provide image_path or set season thumbnail")
    
    request = season.youtube.thumbnails().set(
        videoId=video_id,
        media_body=media_body,
    )
    return request.execute()


def propagate_season_thumbnails_to_matches(season, force_override: bool = False):
    """
    Propagate season thumbnail to matches.
    
    Args:
        season: Season model instance
        force_override: If True, override even matches with custom thumbnails
    """
    if not season.thumbnail_image:
        return
        
    queryset = season.matches.filter(
        videos__isnull=False  # Only matches that have YouTube videos
    ).exclude(videos=[])
    
    if not force_override:
        # Only update matches that don't have their own thumbnail
        queryset = queryset.filter(thumbnail_image__isnull=True)
    
    queryset.update(
        thumbnail_image=season.thumbnail_image,
        thumbnail_image_mimetype=season.thumbnail_image_mimetype
    )