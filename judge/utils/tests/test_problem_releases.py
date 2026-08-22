import json
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase

from judge.utils.problem_releases import activate_release, build_release, verify_sha256


class ProblemReleaseTest(SimpleTestCase):
    def test_build_release_is_versioned_and_verifiable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / 'source'
            source.mkdir()
            (source / 'init.yml').write_text('archive: data.zip\n')
            (source / 'data.zip').write_bytes(b'tests')

            package, manifest_bytes, manifest = build_release(source, 'aplusb', 'v1')
            package_path = Path(temp_dir) / 'package.zip'
            package_path.write_bytes(package)

            self.assertTrue(verify_sha256(package_path, manifest['sha256']))
            self.assertEqual(json.loads(manifest_bytes)['package'], 'releases/aplusb/v1/package.zip')
            with zipfile.ZipFile(package_path) as archive:
                self.assertEqual(archive.namelist(), ['data.zip', 'init.yml'])

    def test_activate_release_keeps_previous_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'problems'
            active = root / 'aplusb'
            active.mkdir(parents=True)
            (active / 'init.yml').write_text('old')
            package = Path(temp_dir) / 'package.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('init.yml', 'new')

            activate_release(package, active, 'aplusb')

            self.assertEqual((active / 'init.yml').read_text(), 'new')
            self.assertEqual((root / '.aplusb.previous' / 'init.yml').read_text(), 'old')

    def test_activate_release_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / 'package.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('../outside', 'bad')

            with self.assertRaises(ValueError):
                activate_release(package, Path(temp_dir) / 'problems' / 'bad', 'bad')
