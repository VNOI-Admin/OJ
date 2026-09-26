import json
import os
import re
import zipfile

import yaml
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import Storage
from django.urls import reverse

from judge.utils.storages import ProblemDataS3Storage, ProblemFileSystemStorage, ProblemStorage


class StorageManager:
    _instance = None

    def __init__(self, backends: dict, default_name: str, metadata_dir: str = None):
        self._backends = backends
        self._default_name = default_name
        self._metadata_dir = metadata_dir

    @classmethod
    def get_instance(cls) -> 'StorageManager':
        if cls._instance is None:
            cls._instance = cls._load()
        return cls._instance

    @classmethod
    def _load(cls) -> 'StorageManager':
        config_path = getattr(settings, 'DMOJ_STORAGE_CONFIG_PATH', None)
        if config_path:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        elif getattr(settings, 'DMOJ_PROBLEM_DATA_ROOT', None):
            config = {
                'default': 'local',
                'storages': {'local': {'backend': 'filesystem', 'location': settings.DMOJ_PROBLEM_DATA_ROOT}},
            }
        else:
            raise ImproperlyConfigured(
                'Set DMOJ_STORAGE_CONFIG_PATH (YAML path) or DMOJ_PROBLEM_DATA_ROOT in settings.',
            )

        storages_conf = config.get('storages', {})
        default_name = config.get('default', '')
        metadata_dir = config.get('metadata_dir', None)

        if not storages_conf:
            raise ImproperlyConfigured('Storage config must define at least one storage under "storages".')
        if not default_name:
            raise ImproperlyConfigured('Storage config must define a "default" storage name.')
        if default_name not in storages_conf:
            raise ImproperlyConfigured(f'Default storage "{default_name}" not found in storages config.')

        backends = {}
        for name, conf in storages_conf.items():
            conf = dict(conf)
            backend = conf.pop('backend', None)
            if backend == 'filesystem':
                storage = ProblemFileSystemStorage(location=conf['location'])
            elif backend == 's3':
                storage = ProblemDataS3Storage(**conf)
            else:
                raise ImproperlyConfigured(f'Unknown storage backend "{backend}" for storage "{name}".')
            backends[name] = storage

        return cls(backends, default_name, metadata_dir)

    def get(self, name: str) -> ProblemStorage:
        try:
            return self._backends[name]
        except KeyError:
            raise ImproperlyConfigured(f'Storage backend "{name}" not found in config.')

    def default(self) -> ProblemStorage:
        return self._backends[self._default_name]

    @property
    def default_name(self) -> str:
        return self._default_name

    @property
    def metadata_dir(self):
        return self._metadata_dir


if os.altsep:
    def split_path_first(path, repath=re.compile('[%s]' % re.escape(os.sep + os.altsep))):
        return repath.split(path, 1)
else:
    def split_path_first(path):
        return path.split(os.sep, 1)


def get_visible_content(archive, filename):
    if archive.getinfo(filename).file_size <= settings.VNOJ_TESTCASE_VISIBLE_LENGTH:
        data = archive.read(filename)
    else:
        data = archive.open(filename).read(settings.VNOJ_TESTCASE_VISIBLE_LENGTH) + b'...'
    return data.decode('utf-8', errors='ignore')


def get_testcase_data(archive, case):
    return {
        'input': get_visible_content(archive, case.input_file),
        'answer': get_visible_content(archive, case.output_file),
    }


def _read_testcases_data(problem, archive):
    testcases_data = {}

    # TODO:
    # - Support manually managed problems
    # - Support pretest
    order = 0
    for case in problem.cases.all().order_by('order'):
        try:
            if not case.input_file:
                continue
            order += 1
            testcases_data[order] = get_testcase_data(archive, case)
        except Exception:
            return {}

    return testcases_data


class ProblemDataStorage(Storage):
    def _get_backend(self, name) -> ProblemStorage:
        from judge.models.problem import Problem  # lazy import to avoid circular
        code = split_path_first(name)[0]
        try:
            sid = Problem.objects.values_list('storage', flat=True).get(code=code)
        except Exception:
            sid = ''
        return StorageManager.get_instance().get(sid or StorageManager.get_instance().default_name)

    def url(self, name):
        path = split_path_first(name)
        if len(path) != 2:
            raise ValueError('This file is not accessible via a URL.')
        return reverse('problem_data_file', args=path)

    def path(self, name):
        return self._get_backend(name).path(name)

    def _open(self, name, mode='rb'):
        return self._get_backend(name).open(name, mode)

    def _save(self, name, content):
        backend = self._get_backend(name)
        return backend._save(name, content)

    def exists(self, name):
        return self._get_backend(name).exists(name)

    def delete(self, name):
        return self._get_backend(name).delete(name)

    def size(self, name):
        return self._get_backend(name).size(name)

    def get_available_name(self, name, max_length=None):
        return name

    def deconstruct(self):
        return ('judge.utils.problem_data.ProblemDataStorage', [], {})

    def rename(self, old, new):
        backend = self._get_backend(new)
        return backend.rename_folder(old, new)

    def presigned_url(self, name, **kwargs):
        backend = self._get_backend(name)
        if hasattr(backend, 'presigned_url'):
            return backend.presigned_url(name, **kwargs)
        return None

    def _build_metadata(self, problem):
        from judge.models import ProblemData

        metadata = {'files': [], 'testcases': {}}
        try:
            data = problem.data_files
        except ProblemData.DoesNotExist:
            return metadata
        if not data.zipfile or not self.exists(data.zipfile.name):
            return metadata

        try:
            with zipfile.ZipFile(self.open(data.zipfile.name)) as archive:
                metadata['files'] = archive.namelist()
                metadata['testcases'] = _read_testcases_data(problem, archive)
        except zipfile.BadZipfile:
            pass
        return metadata

    def _get_metadata_path(self, problem):
        metadata_dir = StorageManager.get_instance().metadata_dir
        if not metadata_dir:
            return None
        return os.path.join(metadata_dir, f'{problem.code}_metadata.json')

    def get_problem_metadata(self, problem):
        path = self._get_metadata_path(problem)
        if path is None:
            return self._build_metadata(problem)

        try:
            with open(path) as f:
                metadata = json.load(f)
            # we expect integers as testcase keys
            metadata['testcases'] = {int(k): v for k, v in metadata['testcases'].items()}
            return metadata
        except (OSError, ValueError, KeyError, AttributeError):
            pass

        metadata = self._build_metadata(problem)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = '%s.%d.tmp' % (path, os.getpid())
        with open(tmp_path, 'w') as f:
            json.dump(metadata, f)
        os.replace(tmp_path, path)
        return metadata

    def invalidate_problem_metadata(self, problem):
        path = self._get_metadata_path(problem)
        if path is None:
            return
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
