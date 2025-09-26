"""
Data migration to convert existing thumbnail URLs to binary thumbnail images.

This migration will:
1. Find Season and Match objects with `live_stream_thumbnail` URLs
2. Download the image content from those URLs
3. Store the binary data in the `live_stream_thumbnail_image` field
4. Preserve the original URL for fallback if needed

Note: The reverse operation is a no-op since we cannot recreate URLs from binary data.
The original URLs could be remote addresses on foreign servers that we cannot reproduce.
"""

import logging
from django.db import migrations
import requests

logger = logging.getLogger(__name__)


def download_thumbnail_from_url(url, timeout=30):
    """
    Download image content from URL and return binary data.

    Args:
        url (str): The URL to download the image from
        timeout (int): Request timeout in seconds

    Returns:
        bytes: Binary image data, or None if download failed
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "vitriolic/1.0 (Thumbnail Migration)",
            },
        )
        response.raise_for_status()

        # Verify it's an image by checking content type
        content_type = response.headers.get("content-type", "").lower()
        if not content_type.startswith("image/"):
            logger.warning(
                "URL does not serve image content: %s (content-type: %s)",
                url,
                content_type,
            )
            return None

        # Check file size (limit to 10MB for safety)
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > 10 * 1024 * 1024:
            logger.warning(
                "Image too large to migrate: %s (%s bytes)", url, content_length
            )
            return None

        return response.content

    except requests.RequestException as e:
        logger.warning("Failed to download thumbnail from %s: %s", url, e)
        return None
    except Exception as e:
        logger.error("Unexpected error downloading %s: %s", url, e)
        return None


def migrate_season_thumbnails(apps, schema_editor):
    """Migrate Season model thumbnails from URL to binary."""
    Season = apps.get_model("competition", "Season")

    seasons_with_urls = Season.objects.filter(
        live_stream_thumbnail__isnull=False,
        live_stream_thumbnail__gt="",
        live_stream_thumbnail_image__isnull=True,
    )

    migrated_count = 0
    failed_count = 0

    logger.info(
        "Found %d seasons with thumbnail URLs to migrate", seasons_with_urls.count()
    )

    for season in seasons_with_urls:
        logger.info(
            "Migrating thumbnail for %r %r: %s",
            season.competition,
            season,
            season.live_stream_thumbnail,
        )

        binary_data = download_thumbnail_from_url(season.live_stream_thumbnail)
        if binary_data:
            season.live_stream_thumbnail_image = binary_data
            season.save(update_fields=["live_stream_thumbnail_image"])
            migrated_count += 1
            logger.info("Successfully migrated thumbnail for Season %s", season.pk)
        else:
            failed_count += 1
            logger.warning("Failed to migrate thumbnail for Season %s", season.pk)

    logger.info(
        "Season thumbnail migration complete: %d successful, %d failed",
        migrated_count,
        failed_count,
    )


def migrate_match_thumbnails(apps, schema_editor):
    """Migrate Match model thumbnails from URL to binary."""
    Match = apps.get_model("competition", "Match")

    matches_with_urls = Match.objects.filter(
        live_stream_thumbnail__isnull=False,
        live_stream_thumbnail__gt="",
        live_stream_thumbnail_image__isnull=True,
    )

    migrated_count = 0
    failed_count = 0

    logger.info(
        "Found %d matches with thumbnail URLs to migrate", matches_with_urls.count()
    )

    for match in matches_with_urls:
        logger.info(
            "Migrating thumbnail for Match %s: %s",
            match.pk,
            match.live_stream_thumbnail,
        )

        binary_data = download_thumbnail_from_url(match.live_stream_thumbnail)
        if binary_data:
            match.live_stream_thumbnail_image = binary_data
            match.save(update_fields=["live_stream_thumbnail_image"])
            migrated_count += 1
            logger.info("Successfully migrated thumbnail for Match %s", match.pk)
        else:
            failed_count += 1
            logger.warning("Failed to migrate thumbnail for Match %s", match.pk)

    logger.info(
        "Match thumbnail migration complete: %d successful, %d failed",
        migrated_count,
        failed_count,
    )


def migrate_thumbnails_forward(apps, schema_editor):
    """
    Forward migration: Convert URL thumbnails to binary data.
    """
    logger.info("Starting thumbnail URL to binary migration")

    # Migrate Season thumbnails
    migrate_season_thumbnails(apps, schema_editor)

    # Migrate Match thumbnails
    migrate_match_thumbnails(apps, schema_editor)

    logger.info("Thumbnail migration completed")




class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0053_add_thumbnail_image_fields"),
    ]

    operations = [
        migrations.RunPython(
            migrate_thumbnails_forward,
            migrations.RunPython.noop,
            hints={"target_db": "default"},
        ),
    ]
