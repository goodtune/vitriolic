import os.path
from urllib.parse import urljoin

from django.core.files.storage import (
    FileSystemStorage as FileSystemStorageBase,
)

from touchtechnology.common.default_settings import STORAGE_FOLDER, STORAGE_URL

__all__ = (
    "FileSystemStorage",
    "MakeDirectoryMixin",
    "OverwriteMixin",
    "WalkMixin",
)


class MakeDirectoryMixin:
    def makedirs(self, name, path=None):
        parts = [p for p in [self.location, path, name] if p]
        directory = os.path.join(*parts)
        os.makedirs(directory)
        return os.path.join(*parts[1:])


class OverwriteMixin:
    def get_available_name(self, name):
        while self.exists(name):
            self.delete(name)
        return name


class WalkMixin:
    def walk(self, top=None):
        """
        Generator that returns tuples similar to the built-in `os.walk`, but
        all paths are calculated from the Storage API `url` method.
        """
        if top is None:
            top = "."

        # determine the directories and files in the present location, and
        # calculate their full path relative to the "top".
        directories, files = self.listdir(top)
        directories.sort()
        files.sort()
        files = [os.path.join(top, name) for name in files]

        # fetch our "url" with respect to this Storage class.
        yield (
            self.url(top),
            zip([self.url(d) for d in directories], directories),
            zip([self.url(f) for f in files], files),
        )

        # for any child directories, recursively descend and repeat.
        for d in directories:
            for triple in self.walk(os.path.join(top, d)):
                yield triple


class FileSystemStorage(MakeDirectoryMixin, WalkMixin, FileSystemStorageBase):
    """
    Django's storage, keeping the site's files in the folder that
    ``TOUCHTECHNOLOGY_STORAGE_FOLDER`` names inside ``MEDIA_ROOT`` and serving
    them from the URL that ``TOUCHTECHNOLOGY_STORAGE_URL`` names inside
    ``MEDIA_URL``. Without those settings it is ``MEDIA_ROOT`` and ``MEDIA_URL``
    themselves. A ``location`` or ``base_url`` given to it takes the setting's
    place.
    """

    def __init__(self, location=None, base_url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if location is None:
            location = STORAGE_FOLDER
        if base_url is None:
            base_url = STORAGE_URL
        # The settings are lazy objects: an unset one is not ``None`` but
        # false, and ``os.path.join`` wants the value, not the object.
        if location:
            self.location = os.path.join(self.location, str(location))
        if base_url:
            self.base_url = urljoin(self.base_url, str(base_url))

    def writable(self, path):
        if not self.exists(self.path(path)):
            raise OSError(2, os.strerror(2), path)
        return os.access(self.path(path), os.W_OK)
