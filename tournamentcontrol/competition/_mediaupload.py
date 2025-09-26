"""
Custom media upload classes for YouTube thumbnail management.

This module provides memory-based media upload classes that are compatible
with the Google API client library, similar to MediaFileUpload but working
with in-memory data instead of files.
"""

import io

import magic
from googleapiclient.http import MediaUpload


class MediaMemoryUpload(MediaUpload):
    """
    A MediaUpload subclass that uploads from in-memory binary data.

    This class mimics the behavior of MediaFileUpload but sources its data
    from memory (e.g., database fields) instead of a file on disk.
    MIME type is automatically detected using the magic library.

    Args:
        data (bytes): The binary data to upload
        chunksize (int): Size of chunks to use for resumable uploads
        resumable (bool): Whether to make the upload resumable
    """

    def __init__(self, data, chunksize=1024 * 1024, resumable=False):
        super().__init__()
        self._data = data
        try:
            self._mimetype = magic.from_buffer(data, mime=True)
        except Exception:
            # Fallback to generic binary type if magic fails
            self._mimetype = "application/octet-stream"
        self._chunksize = chunksize
        self._resumable = resumable
        self._stream = io.BytesIO(data)

    def chunksize(self):
        """Return the upload chunksize."""
        return self._chunksize

    def mimetype(self):
        """Return the mimetype of the upload."""
        return self._mimetype

    def size(self):
        """Return the size of the upload."""
        return len(self._data)

    def resumable(self):
        """Return True if this is a resumable upload."""
        return self._resumable

    def getbytes(self, begin, end):
        """Get bytes from the upload data."""
        self._stream.seek(begin)
        return self._stream.read(end - begin)

    def has_stream(self):
        """Return True if the upload has an associated stream."""
        return True

    def stream(self):
        """Return the upload stream."""
        return self._stream

    def to_json(self):
        """Convert the upload to JSON representation."""
        return {
            "mimetype": self._mimetype,
            "size": self.size(),
            "resumable": self._resumable,
        }
