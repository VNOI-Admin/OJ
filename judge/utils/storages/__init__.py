import errno
import os

from botocore.client import BaseClient as S3Client
from django.core.files.storage import FileSystemStorage, Storage
from storages.backends.s3 import S3Storage as _S3Storage, clean_name


class ProblemStorage(Storage):
    """Base class for problem data storage backends."""
    def rename_folder(self, old_name, new_name):
        raise NotImplementedError()


class ProblemFileSystemStorage(ProblemStorage, FileSystemStorage):
    def rename_folder(self, old_name, new_name):
        old_path = self.path(old_name)
        new_path = self.path(new_name)
        try:
            os.rename(old_path, new_path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        os.rename(old_path, new_path)

    def _save(self, name, content):
        if self.exists(name):
            self.delete(name)
        return super()._save(name, content)


class ProblemDataS3Storage(ProblemStorage, _S3Storage):
    @property
    def _client(self) -> S3Client:
        return self.connection.meta.client

    def _key(self, name):
        return self._normalize_name(clean_name(name))

    def presigned_url(self, name, filename=None, expire=None):
        params = {'Bucket': self.bucket_name, 'Key': self._key(name)}
        if filename:
            params['ResponseContentDisposition'] = 'attachment; filename="%s"' % filename
        return self._client.generate_presigned_url(
            'get_object', Params=params, ExpiresIn=expire or self.querystring_expire,
        )

    def _iter_keys(self, prefix):
        response = self._client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
        if response.get('IsTruncated'):
            raise RuntimeError(f'Problem data prefix `{prefix}` exceeds the single-page S3 listing limit')

        for obj in response.get('Contents', ()):
            yield obj['Key']

    def copy_prefix(self, old, new):
        """Server-side copy every key under old/ to new/, returning the number of keys copied.
        """
        old_key = self._key(old).rstrip('/')
        new_key = self._key(new).rstrip('/')
        count = 0
        for key in self._iter_keys(old_key + '/'):
            # use .copy instead of .copy_object to handle objects over copy limit (5GB)
            self._client.copy(
                CopySource={'Bucket': self.bucket_name, 'Key': key},
                Bucket=self.bucket_name,
                Key='%s/%s' % (new_key, key[len(old_key) + 1:]),
            )
            count += 1
        return count

    def delete_prefix(self, prefix):
        """Delete every key under prefix/, returning the number of keys deleted."""
        keys = list(self._iter_keys(self._key(prefix).rstrip('/') + '/'))
        self._client.delete_objects(
            Bucket=self.bucket_name,
            Delete={'Objects': [{'Key': key} for key in keys]},
        )
        return len(keys)

    def rename_folder(self, old, new):
        self.copy_prefix(old, new)
        self.delete_prefix(old)
