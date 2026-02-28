from django.core.cache import cache


class CacheFactory:
    def __init__(self, key):
        self._key = key

    def get_cache_key(self):
        return self._key

    def get_cache(self):
        return cache.get(self.get_cache_key())

    def set_cache(self, data, timeout_s=3600):
        cache.set(self.get_cache_key(), data, timeout_s)

    def delete_cache(self):
        cache_key = self.get_cache_key()
        cache.delete(cache_key)


def organization_storage_cache_factory(organization_id):
    return CacheFactory(f'org_storage_total_{organization_id}')
