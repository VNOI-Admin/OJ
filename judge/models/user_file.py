import os
import uuid
import mimetypes

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

__all__ = ['user_file_storage', 'UserFile', 'FileUsage']

from django.core.files.storage import default_storage
user_file_storage = default_storage


def user_file_directory(instance, filename):
    """Generate file path using UUID_filename format."""
    base_name = os.path.basename(filename)
    return os.path.join('user_files', f'{instance.uuid}_{base_name}')


class UserFile(models.Model):
    """Model for storing user-uploaded files with metadata and usage tracking."""
    
    FILE_TYPE_CHOICES = (
        ('checker', _('Custom Checker')),
        ('grader', _('Custom Grader')),
        ('header', _('Header File')),
        ('image', _('Image')),
        ('document', _('Document')),
        ('code', _('Code')),
        ('data', _('Test Data')),
        ('other', _('Other')),
    )
    
    # Core identifiers
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey('Profile', verbose_name=_('owner'), related_name='uploaded_files', on_delete=models.CASCADE)
    
    # File storage
    file = models.FileField(
        verbose_name=_('file'),
        storage=user_file_storage,
        upload_to=user_file_directory,
    )
    filename = models.CharField(max_length=255, verbose_name=_('original filename'))
    file_type = models.CharField(
        max_length=20,
        verbose_name=_('file type'),
        choices=FILE_TYPE_CHOICES,
        default='other',
    )
    size = models.BigIntegerField(verbose_name=_('file size in bytes'), default=0)
    
    # Metadata
    description = models.TextField(verbose_name=_('description'), blank=True)
    is_public = models.BooleanField(verbose_name=_('is public'), default=False)
    
    # Timestamps and access tracking
    uploaded_at = models.DateTimeField(verbose_name=_('uploaded at'), auto_now_add=True)
    last_accessed = models.DateTimeField(verbose_name=_('last accessed'), auto_now_add=True)
    access_count = models.IntegerField(verbose_name=_('access count'), default=0)
    
    class Meta:
        verbose_name = _('user file')
        verbose_name_plural = _('user files')
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['user', 'file_type']),
        ]
    
    def __str__(self):
        return f"{self.filename} ({self.user.user.username})"
    
    def save(self, *args, **kwargs):
        """Update file size and ensure filename is set before saving."""
        # Revoke previously shared links when transitioning from public to private.
        if self.pk:
            try:
                previous = UserFile.objects.only('is_public').get(pk=self.pk)
                if previous.is_public and not self.is_public:
                    self.uuid = uuid.uuid4()
            except UserFile.DoesNotExist:
                pass

        if self.file:
            file_basename = os.path.basename(self.file.name)

            # On create, always derive filename from uploaded file to preserve extension.
            if self._state.adding or not self.filename:
                self.filename = file_basename
            # If filename was manually set without extension, append extension from file.
            elif '.' not in os.path.basename(self.filename) and '.' in file_basename:
                _, ext = os.path.splitext(file_basename)
                if ext:
                    self.filename = f'{self.filename}{ext}'
        
        # Update file size if not already set
        if not self.size and self.file:
            try:
                self.size = self.file.size
            except (OSError, IOError):
                self.size = 0
        super().save(*args, **kwargs)
    
    def update_last_accessed(self):
        """Update last_accessed timestamp and increment access count."""
        self.last_accessed = timezone.now()
        self.access_count += 1
        self.save(update_fields=['last_accessed', 'access_count'])
    
    def get_absolute_url(self):
        """Return the absolute URL for this file."""
        return reverse('user_file_detail', kwargs={'uuid': self.uuid})
    
    def get_download_url(self):
        """Return the safe download URL for this file."""
        return reverse('user_file_download', kwargs={'uuid': self.uuid})

    def get_access_url(self):
        """Return the safe inline view URL for this file."""
        return reverse('user_file_access', kwargs={'uuid': self.uuid})

    def get_resolved_filename(self):
        """Return filename with extension recovered from storage path when needed."""
        stored_basename = os.path.basename(self.file.name or '')
        download_name = (self.filename or '').strip()

        if not download_name:
            return stored_basename

        if '.' not in os.path.basename(download_name) and '.' in stored_basename:
            _, ext = os.path.splitext(stored_basename)
            if ext:
                return f'{download_name}{ext}'

        return download_name

    def get_resolved_mime_type(self):
        """Return best-effort MIME type for serving this file."""
        download_name = self.get_resolved_filename()
        mime_type, _ = mimetypes.guess_type(download_name)
        if mime_type:
            return mime_type

        stored_basename = os.path.basename(self.file.name or '')
        mime_type, _ = mimetypes.guess_type(stored_basename)
        return mime_type or 'application/octet-stream'


class FileUsage(models.Model):
    """Model tracking where a file is used in the system."""
    
    USAGE_TYPE_CHOICES = (
        ('problem_checker', _('Problem - Checker')),
        ('problem_grader', _('Problem - Grader')),
        ('problem_header', _('Problem - Header')),
        ('problem_data', _('Problem - Test Data')),
        ('problem_statement_attachment', _('Problem - Statement Attachment')),
        ('submission_attachment', _('Submission - Attachment')),
        ('markdown_content', _('Markdown - Content Image')),
        ('library_personal', _('Library - Personal')),
        ('library_shared', _('Library - Shared')),
        ('other', _('Other')),
    )
    
    file = models.ForeignKey(UserFile, verbose_name=_('file'), related_name='usages', on_delete=models.CASCADE)
    usage_type = models.CharField(
        max_length=50,
        verbose_name=_('usage type'),
        choices=USAGE_TYPE_CHOICES,
        default='other',
    )
    
    # Generic reference fields - can reference problems, submissions, etc.
    problem_id = models.IntegerField(verbose_name=_('problem ID'), null=True, blank=True, db_index=True)
    submission_id = models.IntegerField(verbose_name=_('submission ID'), null=True, blank=True, db_index=True)
    context_description = models.CharField(max_length=255, verbose_name=_('context description'), blank=True)
    
    created_at = models.DateTimeField(verbose_name=_('created at'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('file usage')
        verbose_name_plural = _('file usages')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['file', 'usage_type']),
            models.Index(fields=['problem_id', 'usage_type']),
            models.Index(fields=['submission_id']),
        ]
    
    def __str__(self):
        return f"{self.file.filename} - {self.get_usage_type_display()}"
    
    def get_context_label(self):
        """Return a human-readable label for the usage context."""
        if self.problem_id:
            try:
                from judge.models import Problem
                problem = Problem.objects.get(id=self.problem_id)
                return f"Problem {problem.code}"
            except Exception:
                return f"Problem #{self.problem_id}"
        elif self.submission_id:
            return f"Submission #{self.submission_id}"
        else:
            return self.context_description or self.get_usage_type_display()
