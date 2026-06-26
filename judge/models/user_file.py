import os
import re
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

__all__ = ['user_file_storage', 'UserFileStorage', 'UserFile']


class UserFileStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(settings.MEDIA_ROOT)


user_file_storage = UserFileStorage()


def user_file_directory(instance, filename):
    ext = os.path.splitext(filename)[1]
    if instance.file_scope == UserFile.FileScope.MARTOR and ext.lower() not in settings.MARTOR_UPLOAD_SAFE_EXTS:
        ext = '.png'
    subdir_map = {
        UserFile.FileScope.MARTOR: settings.MARTOR_UPLOAD_MEDIA_DIR,
        UserFile.FileScope.ATTACHMENT: settings.USER_FILE_STORAGE_MEDIA_DIR,
    }
    subdir = subdir_map.get(instance.file_scope, settings.USER_FILE_STORAGE_MEDIA_DIR)
    return os.path.join(subdir, str(uuid.uuid4()) + ext)


class UserFile(models.Model):
    class FileScope(models.TextChoices):
        MARTOR = 'martor', _('Martor Image')
        ATTACHMENT = 'attachment', _('Attachment')

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey(
        'Profile', verbose_name=_('owner'), related_name='uploaded_files',
        on_delete=models.CASCADE, null=True, blank=True,
    )
    file_scope = models.CharField(
        max_length=32,
        choices=FileScope.choices,
        default=FileScope.ATTACHMENT,
        db_index=True,
        verbose_name=_('file scope'),
    )

    file = models.FileField(
        verbose_name=_('file'),
        storage=user_file_storage,
        upload_to=user_file_directory,
    )
    filename = models.CharField(max_length=255, verbose_name=_('original filename'))
    size = models.BigIntegerField(verbose_name=_('file size in bytes'), default=0)
    uploaded_at = models.DateTimeField(verbose_name=_('uploaded at'), auto_now_add=True)

    class Meta:
        verbose_name = _('user file')
        verbose_name_plural = _('user files')
        ordering = ['-uploaded_at']

    def __str__(self):
        user_str = self.user.user.username if self.user_id else 'system'
        return f'{self.filename} ({user_str})'

    @classmethod
    def can_upload_by(cls, user):
        """Whether the user may upload files directly on the /files page."""
        return user.is_authenticated and user.has_perm('judge.add_userfile')

    @staticmethod
    def _profile_id(user):
        if not user.is_authenticated:
            return None
        profile = getattr(user, 'profile', None)
        return getattr(profile, 'id', None)

    def is_owned_by(self, user):
        return self.user_id == self._profile_id(user)

    def can_view_by(self, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return self.is_owned_by(user)

    def can_change_by(self, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return self.is_owned_by(user)

    def can_delete_by(self, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return self.is_owned_by(user)

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
        if self.filename:
            self.filename = re.sub(r'[^a-zA-Z0-9_\-.]', '_', self.filename)
        if not self.size and self.file:
            try:
                self.size = self.file.size
            except (OSError, IOError):
                self.size = 0
        super().save(*args, **kwargs)

    def get_file_path(self):
        return user_file_storage.path(self.file.name)

    def get_url_path(self):
        if self.file_scope == self.FileScope.MARTOR:
            return None  # nginx serves directly; no X-Accel-Redirect needed
        internal_base = settings.USER_FILE_STORAGE_INTERNAL
        return '{}/{}'.format(internal_base, self.file.name) if internal_base else None

    def get_access_url(self):
        if self.file_scope == self.FileScope.MARTOR:
            name = os.path.basename(self.file.name)
            url_base = getattr(settings, 'MARTOR_UPLOAD_URL_PREFIX', '/martor')
            return url_base.rstrip('/') + '/' + name
        return reverse('user_file_access', kwargs={'uuid': self.uuid})
