import os
import re

import yaml
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage, Storage
from django.urls import reverse


class StorageManager:
    _instance = None

    def __init__(self, backends: dict, default_name: str):
        self._backends = backends
        self._default_name = default_name

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

        if not storages_conf:
            raise ImproperlyConfigured('Storage config must define at least one storage under "storages".')
        if not default_name:
            raise ImproperlyConfigured('Storage config must define a "default" storage name.')
        if default_name not in storages_conf:
            raise ImproperlyConfigured(f'Default storage "{default_name}" not found in storages config.')

        backends = {}
        for name, conf in storages_conf.items():
            backend = conf.get('backend')
            if backend == 'filesystem':
                backends[name] = FileSystemStorage(location=conf['location'])
            else:
                raise ImproperlyConfigured(f'Unknown storage backend "{backend}" for storage "{name}".')

        return cls(backends, default_name)

    def get(self, name: str) -> Storage:
        try:
            return self._backends[name]
        except KeyError:
            raise ImproperlyConfigured(f'Storage backend "{name}" not found in config.')

    def default(self) -> Storage:
        return self._backends[self._default_name]

    @property
    def default_name(self) -> str:
        return self._default_name


if os.altsep:
    def split_path_first(path, repath=re.compile('[%s]' % re.escape(os.sep + os.altsep))):
        return repath.split(path, 1)
else:
    def split_path_first(path):
        return path.split(os.sep, 1)


class ProblemDataStorage(Storage):
    def _get_backend(self, name):
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
        if backend.exists(name):
            backend.delete(name)
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
        backend = self._get_backend(old)
        os.rename(backend.path(old), backend.path(new))
