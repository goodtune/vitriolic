import os.path
import tempfile

from django.test import TestCase
from touchtechnology.common.storage import FileSystemStorage


class StorageTests(TestCase):

    def setUp(self):
        location = tempfile.mkdtemp()
        self.storage = FileSystemStorage(location=location)

    def test_makedirs(self):
        path, folder = '', 'test_mkdir_folder/with_two/subfolders'
        self.assertEqual(self.storage.listdir(path), ([], []))
        self.storage.makedirs(folder)
        self.assertEqual(
            self.storage.listdir(os.path.dirname(folder)),
            ([os.path.basename(folder)], []))
        self.assertEqual(
            self.storage.listdir(
                os.path.dirname(os.path.dirname(folder))),
            ([os.path.basename(os.path.dirname(folder))], []))

    def test_mkdir(self):
        path, folder = '', 'test_mkdir_folder'
        self.assertEqual(self.storage.listdir(path), ([], []))
        self.storage.mkdir(folder)
        self.assertEqual(self.storage.listdir(path), ([folder], []))
        self.assertEqual(self.storage.listdir(folder), ([], []))

    def test_mkdir_path(self):
        path, folder = 'path', 'test_mkdir_path_folder'
        self.storage.mkdir(path)
        self.assertEqual(self.storage.listdir(path), ([], []))
        self.storage.mkdir(folder, path)
        self.assertEqual(self.storage.listdir(path), ([folder], []))
        self.assertEqual(
            self.storage.listdir(os.path.join(path, folder)),
            ([], []))

    def test_path(self):
        filename = 'test_path/to/file.txt'
        self.assertEqual(
            self.storage.path(filename),
            os.path.join(self.storage.location, filename))

    def test_rmdir(self):
        path, folder = '', 'test_rmdir'
        with self.assertRaises(OSError) as cm:
            self.storage.rmdir(folder)
        self.assertEqual(cm.exception.errno, 2)
        self.storage.mkdir(folder)
        self.assertEqual(self.storage.listdir(path), ([folder], []))
        self.storage.rmdir(folder)
        self.assertEqual(self.storage.listdir(path), ([], []))

    def test_rmdir_subdir(self):
        folder = 'test_rmdir_subdir'
        subdir = os.path.join(folder, 'subdir')
        self.storage.makedirs(subdir)
        with self.assertRaises(OSError):
            self.storage.rmdir(folder)

    def test_writable(self):
        folder = 'test_writable'
        with self.assertRaises(OSError) as cm:
            self.storage.writable(folder)
        self.assertEqual(cm.exception.errno, 2)
        self.storage.mkdir(folder)
        self.assertTrue(self.storage.writable(folder))
