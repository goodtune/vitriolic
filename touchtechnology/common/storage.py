import logging
import os.path

from django.core.files.storage import FileSystemStorage as FileSystemStorageBase
from django.utils.six.moves.urllib.parse import urljoin
from touchtechnology.common.default_settings import STORAGE_FOLDER, STORAGE_URL

try:
    from tenant_schemas.storage import TenantStorageMixin
except ImportError:
    TenantStorageMixin = type('TenantStorageMixin', (), {})


logger = logging.getLogger(__name__)

__all__ = (
    'FileSystemStorage',
    'MakeDirectoryMixin',
    'OverwriteMixin',
    'WalkMixin',
)


class MakeDirectoryMixin(object):

    def makedirs(self, name, path=None):
        parts = list(filter(None, (self.location, path, name)))
        directory = os.path.join(*parts)
        os.makedirs(directory)
        return os.path.join(*parts[1:])

    def mkdir(self, name, path=None):
        directory = self.path(os.path.join(
            *list(filter(None, (path, name)))))
        os.mkdir(directory)
        if path is None:
            return name
        return os.path.join(path, name)

    def rmdir(self, path):
        directory = self.path(path)
        os.rmdir(directory)


class OverwriteMixin(object):

    def get_available_name(self, name):
        while self.exists(name):
            self.delete(name)
        return name


class WalkMixin(object):

    def walk(self, top=None):
        """
        Generator that returns tuples similar to the built-in `os.walk`, but
        all paths are calculated from the Storage API `url` method.
        """
        if top is None:
            top = '.'

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


class FileSystemStorage(MakeDirectoryMixin, WalkMixin, TenantStorageMixin,
                        FileSystemStorageBase):

    def __init__(self, location=STORAGE_FOLDER, base_url=STORAGE_URL,
                 *args, **kwargs):
        super(FileSystemStorage, self).__init__(*args, **kwargs)
        if location is not None:
            self.location = os.path.join(self.location, location)
        if base_url is not None:
            self.base_url = urljoin(self.base_url, base_url)

    def writable(self, path):
        if not self.exists(self.path(path)):
            raise OSError(2, os.strerror(2), path)
        return os.access(self.path(path), os.W_OK)
