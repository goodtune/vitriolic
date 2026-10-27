import os.path
import tempfile

from django.core.files.storage import (
    FileSystemStorage as FileSystemStorageBase,
)
from django.test import TestCase, override_settings

from touchtechnology.common.storage import (
    FileSystemStorage,
    MakeDirectoryMixin,
    WalkMixin,
)


class StorageTests(TestCase):

    def setUp(self):
        location = tempfile.mkdtemp()
        self.storage = FileSystemStorage(location=location)

    def test_bases_are_the_two_mixins_and_the_django_storage(self):
        # No stand-in for a tenant storage mixin sits between them (#546).
        self.assertEqual(
            FileSystemStorage.__bases__,
            (MakeDirectoryMixin, WalkMixin, FileSystemStorageBase),
        )

    def test_makedirs(self):
        path, folder = "", "test_mkdir_folder/with_two/subfolders"
        self.assertEqual(self.storage.listdir(path), ([], []))
        self.storage.makedirs(folder)
        self.assertEqual(
            self.storage.listdir(os.path.dirname(folder)),
            ([os.path.basename(folder)], []),
        )
        self.assertEqual(
            self.storage.listdir(os.path.dirname(os.path.dirname(folder))),
            ([os.path.basename(os.path.dirname(folder))], []),
        )

    def test_mkdir(self):
        path, folder = "", "test_mkdir_folder"
        self.assertEqual(self.storage.listdir(path), ([], []))
        self.storage.mkdir(folder)
        self.assertEqual(self.storage.listdir(path), ([folder], []))
        self.assertEqual(self.storage.listdir(folder), ([], []))

    def test_mkdir_path(self):
        path, folder = "path", "test_mkdir_path_folder"
        self.storage.mkdir(path)
        self.assertEqual(self.storage.listdir(path), ([], []))
        self.storage.mkdir(folder, path)
        self.assertEqual(self.storage.listdir(path), ([folder], []))
        self.assertEqual(self.storage.listdir(os.path.join(path, folder)), ([], []))

    def test_path(self):
        filename = "test_path/to/file.txt"
        self.assertEqual(
            self.storage.path(filename), os.path.join(self.storage.location, filename)
        )

    def test_rmdir(self):
        path, folder = "", "test_rmdir"
        with self.assertRaises(OSError) as cm:
            self.storage.rmdir(folder)
        self.assertEqual(cm.exception.errno, 2)
        self.storage.mkdir(folder)
        self.assertEqual(self.storage.listdir(path), ([folder], []))
        self.storage.rmdir(folder)
        self.assertEqual(self.storage.listdir(path), ([], []))

    def test_rmdir_subdir(self):
        folder = "test_rmdir_subdir"
        subdir = os.path.join(folder, "subdir")
        self.storage.makedirs(subdir)
        with self.assertRaises(OSError):
            self.storage.rmdir(folder)

    def test_writable(self):
        folder = "test_writable"
        with self.assertRaises(OSError) as cm:
            self.storage.writable(folder)
        self.assertEqual(cm.exception.errno, 2)
        self.storage.mkdir(folder)
        self.assertEqual(self.storage.writable(folder), True)


class StorageSettingsTests(TestCase):
    """
    Where the storage keeps the site's files: ``MEDIA_ROOT`` and ``MEDIA_URL``,
    or the folder and the URL that ``TOUCHTECHNOLOGY_STORAGE_FOLDER`` and
    ``TOUCHTECHNOLOGY_STORAGE_URL`` name inside them.
    """

    def setUp(self):
        self.root = self.enterContext(tempfile.TemporaryDirectory())

    def test_without_the_settings_the_storage_is_the_media_root(self):
        with override_settings(MEDIA_ROOT=self.root, MEDIA_URL="/media/"):
            storage = FileSystemStorage()
            self.assertEqual(storage.location, self.root)
            self.assertEqual(storage.base_url, "/media/")

    def test_the_storage_folder_is_inside_the_media_root(self):
        with override_settings(
            MEDIA_ROOT=self.root, TOUCHTECHNOLOGY_STORAGE_FOLDER="uploads"
        ):
            self.assertEqual(
                FileSystemStorage().location, os.path.join(self.root, "uploads")
            )

    def test_the_storage_url_is_inside_the_media_url(self):
        with override_settings(
            MEDIA_URL="/media/", TOUCHTECHNOLOGY_STORAGE_URL="uploads/"
        ):
            self.assertEqual(FileSystemStorage().base_url, "/media/uploads/")

    def test_both_settings_place_the_storage_inside_the_media(self):
        with override_settings(
            MEDIA_ROOT=self.root,
            MEDIA_URL="/media/",
            TOUCHTECHNOLOGY_STORAGE_FOLDER="uploads",
            TOUCHTECHNOLOGY_STORAGE_URL="uploads/",
        ):
            storage = FileSystemStorage()
            self.assertEqual(storage.location, os.path.join(self.root, "uploads"))
            self.assertEqual(storage.base_url, "/media/uploads/")

    def test_a_location_given_to_the_storage_takes_the_settings_place(self):
        with override_settings(TOUCHTECHNOLOGY_STORAGE_FOLDER="uploads"):
            self.assertEqual(FileSystemStorage(location=self.root).location, self.root)
