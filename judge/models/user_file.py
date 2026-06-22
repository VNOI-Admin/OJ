import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

__all__ = ['user_file_storage', 'UserFileStorage', 'UserFile']


class UserFileStorage(FileSystemStorage):
    def __init__(self):
        location = os.path.join(settings.MEDIA_ROOT, settings.USER_FILE_STORAGE_MEDIA_DIR)
        super().__init__(location)


user_file_storage = UserFileStorage()


def user_file_directory(instance, filename):
    return str(uuid.uuid4())


class UserFile(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey(
        'Profile', verbose_name=_('owner'), related_name='uploaded_files', on_delete=models.CASCADE,
    )

    file = models.FileField(
        verbose_name=_('file'),
        storage=user_file_storage,
        upload_to=user_file_directory,
    )
    filename = models.CharField(max_length=255, verbose_name=_('original filename'))
    size = models.BigIntegerField(verbose_name=_('file size in bytes'), default=0)
    is_public = models.BooleanField(verbose_name=_('is public'), default=False)

    uploaded_at = models.DateTimeField(verbose_name=_('uploaded at'), auto_now_add=True)

    class Meta:
        verbose_name = _('user file')
        verbose_name_plural = _('user files')
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.filename} ({self.user.user.username})'

    @classmethod
    def can_list_by(cls, user):
        """Whether the user may browse the file management list at /files."""
        return user.is_authenticated and user.has_perm('judge.view_userfile')

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
        if self.is_public:
            return True
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
            for ch in ('"', '\\', '\r', '\n'):
                self.filename = self.filename.replace(ch, '')
        if not self.size and self.file:
            try:
                self.size = self.file.size
            except (OSError, IOError):
                self.size = 0
        super().save(*args, **kwargs)

    def get_file_path(self):
        return user_file_storage.path(self.file.name)

    def get_url_path(self):
        internal_base = settings.USER_FILE_STORAGE_INTERNAL
        return '{}/{}'.format(internal_base, self.file.name) if internal_base else None

    def get_access_url(self):
        return reverse('user_file_access', kwargs={'uuid': self.uuid})
