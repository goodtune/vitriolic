import logging
import os.path
from urllib.parse import urljoin

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage as FileSystemStorageBase
from django.db.models.fields.files import ImageFieldFile
from PIL import Image
from touchtechnology.common.default_settings import STORAGE_FOLDER, STORAGE_URL

try:
    from tenant_schemas.storage import TenantStorageMixin
except ImportError:
    TenantStorageMixin = type("TenantStorageMixin", (), {})


logger = logging.getLogger(__name__)

__all__ = (
    "FileSystemStorage",
    "MakeDirectoryMixin",
    "OverwriteMixin",
    "ResizedImageFieldFile",
    "WalkMixin",
)


class MakeDirectoryMixin(object):
    def makedirs(self, name, path=None):
        parts = [p for p in [self.location, path, name] if p]
        directory = os.path.join(*parts)
        os.makedirs(directory)
        return os.path.join(*parts[1:])

    def mkdir(self, name, path=None):
        directory = self.path(os.path.join(*[p for p in [path, name] if p]))
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


class FileSystemStorage(
    MakeDirectoryMixin, WalkMixin, TenantStorageMixin, FileSystemStorageBase
):
    def __init__(self, location=STORAGE_FOLDER, base_url=STORAGE_URL, *args, **kwargs):
        super(FileSystemStorage, self).__init__(*args, **kwargs)
        if location is not None:
            self.location = os.path.join(self.location, location)
        if base_url is not None:
            self.base_url = urljoin(self.base_url, base_url)

    def writable(self, path):
        if not self.exists(self.path(path)):
            raise OSError(2, os.strerror(2), path)
        return os.access(self.path(path), os.W_OK)


class ResizedImageFieldFile(ImageFieldFile):
    def __init__(self, instance, field_name, size, background):
        self.field_name = field_name
        self.maxwidth, self.maxheight = size
        self.background = background
        field = instance._meta.get_field(field_name)
        path, filename = os.path.split(getattr(instance, field_name).name)
        dim = "%sx%s" % (self.maxwidth, self.maxheight)
        name = os.path.join(path, dim, "%s.jpg" % instance.pk)
        super(ResizedImageFieldFile, self).__init__(instance, field, name)

    def regenerate(self):
        image_field = getattr(self.instance, self.field_name)
        if not self.storage.exists(image_field):
            logger.warning(
                'Original file "{0}" does not exist, failed to '
                "regenerate sized image.".format(image_field)
            )
            return

        path = os.path.dirname(self.name)
        if not self.storage.exists(path):
            self.storage.makedirs(path)

        original = self.storage.open(image_field)
        image = Image.open(original)
        if image.mode != "RGB":
            image = image.convert("RGB")

        # determine the dimensions of the original image
        (__, __, w, h) = image.getbbox()

        # determine the new width & height for the image dimensions
        adjusted_width = int(w * (float(self.maxheight) / float(h)))
        adjusted_height = int(h * (float(self.maxwidth) / float(w)))

        # scale the image to the new size
        x_scale = min(self.maxwidth, adjusted_width)
        y_scale = min(self.maxheight, adjusted_height)
        small = image.resize((x_scale, y_scale), Image.ANTIALIAS)

        # create a new image object onto which we will paste the
        # resized original
        dim = (self.maxwidth, self.maxheight)
        thumbnail = Image.new("RGB", dim, self.background)

        # paste the resized image onto the thumbnail canvas
        x_offset = self.maxwidth - x_scale // 2
        y_offset = max(0, self.maxheight - y_scale // 2)
        offset = (x_offset, y_offset)
        thumbnail.paste(small, offset)

        f = ContentFile(thumbnail.tostring("jpeg", "RGB"))
        self.storage.save(self.name, f)
