from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

__all__ = ['AttachmentMixin', 'FileAttachment']


class AttachmentMixin:
    def can_view_attachment_by(self, user) -> bool:
        raise NotImplementedError(
            f'{self.__class__.__name__} must implement can_view_attachment_by(user)'
        )


class FileAttachment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    linked_item = GenericForeignKey('content_type', 'object_id')

    file = models.ForeignKey(
        'UserFile',
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name=_('file'),
    )
    display_name = models.CharField(max_length=255, blank=True, verbose_name=_('display name'))

    class Meta:
        verbose_name = _('file attachment')
        verbose_name_plural = _('file attachments')

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        return self.display_name or self.file.filename

    def can_view_by(self, user):
        parent = self.linked_item
        if parent is None:
            return False
        return parent.can_view_attachment_by(user)
