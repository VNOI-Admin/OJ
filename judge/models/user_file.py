import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

__all__ = [
    'user_file_storage', 'UserFileStorage', 'UserFile', 'FileUsage']

USER_FILE_STORAGE_SCOPE_PROBLEM = 'problem'
USER_FILE_STORAGE_SCOPE_CONTEST = 'contest'
# Self-uploads via /files, and any markdown upload not tied to a problem/contest.
USER_FILE_STORAGE_SCOPE_USER = 'user'

USER_FILE_STORAGE_SCOPE_CHOICES = (
    (USER_FILE_STORAGE_SCOPE_PROBLEM, _('Problem')),
    (USER_FILE_STORAGE_SCOPE_CONTEST, _('Contest')),
    (USER_FILE_STORAGE_SCOPE_USER, _('User upload')),
)
USER_FILE_STORAGE_SCOPE_VALUES = frozenset(value for value, _ in USER_FILE_STORAGE_SCOPE_CHOICES)
USER_FILE_CONTEXT_SCOPES = frozenset((
    USER_FILE_STORAGE_SCOPE_PROBLEM,
    USER_FILE_STORAGE_SCOPE_CONTEST,
))


class UserFileStorage(FileSystemStorage):
    def __init__(self):
        location = os.path.join(settings.MEDIA_ROOT, settings.USER_FILE_STORAGE_MEDIA_DIR)
        super().__init__(location)


user_file_storage = UserFileStorage()


def user_file_directory(instance, filename):
    scope = getattr(instance, 'storage_scope', None) or USER_FILE_STORAGE_SCOPE_USER
    if scope not in USER_FILE_STORAGE_SCOPE_VALUES:
        scope = USER_FILE_STORAGE_SCOPE_USER

    return os.path.join(scope, str(uuid.uuid4()))


class UserFile(models.Model):
    STORAGE_SCOPE_PROBLEM = USER_FILE_STORAGE_SCOPE_PROBLEM
    STORAGE_SCOPE_CONTEST = USER_FILE_STORAGE_SCOPE_CONTEST
    STORAGE_SCOPE_USER = USER_FILE_STORAGE_SCOPE_USER

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
    storage_scope = models.CharField(
        max_length=20,
        verbose_name=_('storage scope'),
        choices=USER_FILE_STORAGE_SCOPE_CHOICES,
        default=USER_FILE_STORAGE_SCOPE_USER,
        db_index=True,
    )
    size = models.BigIntegerField(verbose_name=_('file size in bytes'), default=0)
    is_public = models.BooleanField(verbose_name=_('is public'), default=False)

    uploaded_at = models.DateTimeField(verbose_name=_('uploaded at'), auto_now_add=True)
    last_accessed = models.DateTimeField(verbose_name=_('last accessed'), auto_now_add=True)
    access_count = models.IntegerField(verbose_name=_('access count'), default=0)

    class Meta:
        verbose_name = _('user file')
        verbose_name_plural = _('user files')
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['storage_scope', '-uploaded_at']),
        ]

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

    @property
    def requires_context_authorization(self):
        return self.storage_scope in USER_FILE_CONTEXT_SCOPES

    def can_view_by_problem_context(self, user):
        problem_ids = list(self.usages.exclude(problem_id__isnull=True).values_list('problem_id', flat=True))
        if not problem_ids:
            return False

        from judge.models import Problem

        for problem in Problem.objects.filter(id__in=problem_ids):
            if problem.is_accessible_by(user, skip_contest_problem_check=True):
                return True
        return False

    def can_view_by_contest_context(self, user):
        contest_ids = list(self.usages.exclude(contest_id__isnull=True).values_list('contest_id', flat=True))
        if not contest_ids:
            return False

        from judge.models import Contest

        for contest in Contest.objects.filter(id__in=contest_ids):
            if contest.is_accessible_by(user):
                return True
        return False

    def can_view_by_context(self, user):
        contest_access = self.can_view_by_contest_context(user)
        problem_access = self.can_view_by_problem_context(user)

        if self.storage_scope == USER_FILE_STORAGE_SCOPE_CONTEST:
            return contest_access or problem_access
        if self.storage_scope == USER_FILE_STORAGE_SCOPE_PROBLEM:
            return problem_access or contest_access
        return contest_access or problem_access

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

    def update_last_accessed(self):
        # Atomic, read-free increment so concurrent downloads don't lose counts.
        now = timezone.now()
        UserFile.objects.filter(pk=self.pk).update(
            last_accessed=now,
            access_count=F('access_count') + 1,
        )
        self.last_accessed = now
        self.access_count += 1

    def get_file_path(self):
        return user_file_storage.path(self.file.name)

    def get_url_path(self):
        internal_base = settings.USER_FILE_STORAGE_INTERNAL
        return '{}/{}'.format(internal_base, self.file.name) if internal_base else None

    def get_access_url(self):
        return reverse('user_file_access', kwargs={'uuid': self.uuid})


class FileUsage(models.Model):
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

    problem_id = models.IntegerField(verbose_name=_('problem ID'), null=True, blank=True, db_index=True)
    contest_id = models.IntegerField(verbose_name=_('contest ID'), null=True, blank=True, db_index=True)
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
            models.Index(fields=['contest_id', 'usage_type']),
            models.Index(fields=['submission_id']),
        ]

    def __str__(self):
        return f'{self.file.filename} - {self.get_usage_type_display()}'

    def get_context_label(self):
        if self.problem_id:
            try:
                from judge.models import Problem
                problem = Problem.objects.get(id=self.problem_id)
                return f'Problem {problem.code}'
            except Exception:
                return f'Problem #{self.problem_id}'
        elif self.contest_id:
            try:
                from judge.models import Contest
                contest = Contest.objects.get(id=self.contest_id)
                return f'Contest {contest.key}'
            except Exception:
                return f'Contest #{self.contest_id}'
        elif self.submission_id:
            return f'Submission #{self.submission_id}'
        else:
            return self.context_description or self.get_usage_type_display()


def _move_user_file_to_scope(user_file, scope):
    """Set a file's storage scope and relocate it on disk into the scope folder.

    Relocation is best-effort: the URL is UUID-based, so a failed move never
    breaks access — the scope (the source-of-truth for tracking) is still saved.
    """
    if user_file.storage_scope == scope:
        return
    user_file.storage_scope = scope

    storage = user_file.file.storage
    old_name = user_file.file.name
    try:
        new_name = user_file_directory(user_file, os.path.basename(old_name))
        if old_name and new_name != old_name and storage.exists(old_name):
            with storage.open(old_name, 'rb') as fh:
                saved_name = storage.save(new_name, fh)
            user_file.file.name = saved_name
            user_file.save(update_fields=['storage_scope', 'file'])
            storage.delete(old_name)
            return
    except Exception:
        pass
    user_file.save(update_fields=['storage_scope'])
