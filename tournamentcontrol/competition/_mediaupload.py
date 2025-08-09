"""
Custom media upload classes for YouTube thumbnail management.

This module provides memory-based media upload classes that are compatible
with the Google API client library, similar to MediaFileUpload but working
with in-memory data instead of files.
"""

import io
from googleapiclient.http import HttpRequest, MediaUpload


class MediaMemoryUpload(MediaUpload):
    """
    A MediaUpload subclass that uploads from in-memory binary data.
    
    This class mimics the behavior of MediaFileUpload but sources its data
    from memory (e.g., database fields) instead of a file on disk.
    
    Args:
        data (bytes): The binary data to upload
        mimetype (str): The MIME type of the data
        chunksize (int): Size of chunks to use for resumable uploads
        resumable (bool): Whether to make the upload resumable
    """
    
    def __init__(self, data, mimetype, chunksize=1024*1024, resumable=False):
        super().__init__()
        self._data = data
        self._mimetype = mimetype
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
            'mimetype': self._mimetype,
            'size': self.size(),
            'resumable': self._resumable,
        }
        
    @classmethod
    def from_bytes(cls, data, mimetype=None, **kwargs):
        """
        Create a MediaMemoryUpload from bytes data.
        
        Args:
            data (bytes): The binary data to upload
            mimetype (str, optional): The MIME type of the data. If not provided,
                                    will be detected using magic library.
            **kwargs: Additional arguments passed to MediaMemoryUpload
            
        Returns:
            MediaMemoryUpload instance or None if no image data available
        """
        if not data:
            return None
            
        if not mimetype:
            # Auto-detect MIME type using magic library
            import magic
            mimetype = magic.from_buffer(data, mime=True)
            
        return cls(data, mimetype, **kwargs)