"""
Custom media upload classes for YouTube thumbnail management.

This module provides database-sourced media upload classes that are compatible
with the Google API client library, similar to MediaFileUpload but reading
data from Django model fields instead of files.
"""

import io
from googleapiclient.http import HttpRequest, MediaUpload


class MediaDatabaseUpload(MediaUpload):
    """
    A MediaUpload subclass that uploads from database-stored binary data.
    
    This class mimics the behavior of MediaFileUpload but sources its data
    from a Django model's BinaryField instead of a file on disk.
    
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
    def from_model_field(cls, obj, image_field_name='thumbnail_image', 
                        mimetype_field_name='thumbnail_image_mimetype', **kwargs):
        """
        Create a MediaDatabaseUpload from Django model fields.
        
        Args:
            obj: Django model instance containing the image data
            image_field_name: Name of the BinaryField containing image data
            mimetype_field_name: Name of the CharField containing MIME type
            **kwargs: Additional arguments passed to MediaDatabaseUpload
            
        Returns:
            MediaDatabaseUpload instance or None if no image data available
            
        Raises:
            ValueError: If image data exists but no MIME type is specified
        """
        image_data = getattr(obj, image_field_name)
        mimetype = getattr(obj, mimetype_field_name)
        
        if not image_data:
            return None
            
        if not mimetype:
            raise ValueError(f"Image data exists but no MIME type specified in {mimetype_field_name}")
            
        return cls(image_data, mimetype, **kwargs)