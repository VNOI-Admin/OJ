from django.core.cache import cache


class CacheFactory:
    def __init__(self, key, default_timeout=86400):
        self._key = key
        self._default_timeout = default_timeout

    def get_cache_key(self):
        return self._key

    def get_cache(self):
        return cache.get(self.get_cache_key())

    def set_cache(self, data, timeout_s=None):
        cache.set(self.get_cache_key(), data,
                  self._default_timeout if timeout_s is None else timeout_s)

    def delete_cache(self):
        cache.delete(self.get_cache_key())


def unread_notification_count_cache_factory(profile_id, timeout=86400):
    return CacheFactory(f'unread_notification_count{profile_id}', default_timeout=timeout)


def bulk_invalidate_notification_caches(profile_ids):
    """Delete unread count caches for many profiles in one round-trip."""
    cache.delete_many([f'unread_notification_count{pid}' for pid in profile_ids])


def storage_pie_cache_factory(org_id):
    return CacheFactory(f'storage_pie_data_{org_id}', default_timeout=7 * 86400)
