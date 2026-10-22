import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.updates import check_package


class Context:
    def check_cancel(self):
        pass


class PackageCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'candidate.deb'
        self.payload = b'fixture package bytes'
        self.path.write_bytes(self.payload)
        self.info = {'version': '0.5.3', 'deb': {'sha256': hashlib.sha256(self.payload).hexdigest()}}
        self.run = patch('modules.updates.subprocess.run', side_effect=[
            SimpleNamespace(stdout='Package: pcmonitor\nVersion: 0.5.3\nArchitecture: all\n'),
            SimpleNamespace(stdout='amd64\n')])
        self.run_mock=self.run.start(); self.addCleanup(self.run.stop)

    def test_accepts_matching_package_hash_version_and_architecture(self):
        with patch('modules.updates.PROJECT', {'deb': {'package': 'pcmonitor'}}):
            self.assertIsNone(check_package(self.path, self.info, Context()))
        self.assertEqual(self.run_mock.call_count, 2)

    def test_rejects_checksum_before_reading_package_metadata(self):
        wrong = dict(self.info, deb={'sha256': '0' * 64})
        with patch('modules.updates.PROJECT', {'deb': {'package': 'pcmonitor'}}):
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                check_package(self.path, wrong, Context())
        self.run_mock.assert_not_called()

    def test_rejects_missing_or_invalid_hash_metadata(self):
        for deb in ({}, {'sha256': 'not-a-hash'}):
            with patch('modules.updates.PROJECT', {'deb': {'package': 'pcmonitor'}}):
                with self.assertRaisesRegex(ValueError, 'Prüfsummenangaben'):
                    check_package(self.path, {'version': '0.5.3', 'deb': deb}, Context())
        self.run_mock.assert_not_called()

    def test_rejects_missing_or_invalid_project_package_id(self):
        for package in (None, 'PC Monitor', '../pcmonitor'):
            with patch('modules.updates.PROJECT', {'deb': {'package': package}}):
                with self.assertRaisesRegex(ValueError, 'Paketkennung'):
                    check_package(self.path, self.info, Context())
        self.run_mock.assert_not_called()

    def test_rejects_wrong_name_version_or_architecture(self):
        for fields in (
            'Package: another\nVersion: 0.5.3\nArchitecture: all\n',
            'Package: pcmonitor\nVersion: 0.5.2\nArchitecture: all\n',
            'Package: pcmonitor\nVersion: 0.5.3\nArchitecture: arm64\n',
        ):
            self.run.stop()
            self.run = patch('modules.updates.subprocess.run', side_effect=[
                SimpleNamespace(stdout=fields), SimpleNamespace(stdout='amd64\n')])
            self.run_mock=self.run.start()
            with patch('modules.updates.PROJECT', {'deb': {'package': 'pcmonitor'}}):
                with self.assertRaisesRegex(ValueError, 'Wrong package'):
                    check_package(self.path, self.info, Context())
        self.run.stop()


if __name__ == '__main__':
    unittest.main()
