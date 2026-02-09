import errno
import os

from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from judge.utils.problem_data import ProblemDataStorage

__all__ = ['problem_data_storage', 'problem_directory_file', 'ProblemData', 'ProblemTestCase', 'CHECKERS']

problem_data_storage = ProblemDataStorage()


def _problem_directory_file(code, filename):
    return os.path.join(code, os.path.basename(filename))


def problem_directory_file(data, filename):
    return _problem_directory_file(data.problem.code, filename)


CHECKERS = (
    ('standard', _('Standard')),
    ('bridged', _('Custom checker')),
    ('floats', _('Floats')),
    ('floatsabs', _('Floats (absolute)')),
    ('floatsrel', _('Floats (relative)')),
    ('identical', _('Byte identical')),
    ('linecount', _('Line-by-line')),
)

GRADERS = (
    ('standard', _('Standard')),
    ('interactive', _('Interactive')),
    ('signature', _('Function Signature Grading (IOI-style)')),
    ('output_only', _('Output Only')),
)

IO_METHODS = (
    ('standard', _('Standard Input/Output')),
    ('file', _('Via files')),
)

CUSTOM_CHECKERS = (
    ('themis', _('Themis checker')),
    ('testlib', _('Testlib checker')),
    ('cms', _('CMS checker')),
    ('coci', _('COCI checker')),
    ('peg', _('PEG checker')),
    ('default', _('DMOJ checker')),
)


class ProblemData(models.Model):
    problem = models.OneToOneField('Problem', verbose_name=_('problem'), related_name='data_files',
                                   on_delete=models.CASCADE)
    zipfile = models.FileField(verbose_name=_('data zip file'), storage=problem_data_storage, null=True, blank=True,
                               upload_to=problem_directory_file)
    generator = models.FileField(verbose_name=_('generator file'), storage=problem_data_storage, null=True, blank=True,
                                 upload_to=problem_directory_file)
    output_prefix = models.IntegerField(verbose_name=_('output prefix length'), blank=True, null=True)
    output_limit = models.IntegerField(verbose_name=_('output limit length'), blank=True, null=True)
    feedback = models.TextField(verbose_name=_('init.yml generation feedback'), blank=True)
    checker = models.CharField(max_length=10, verbose_name=_('checker'), choices=CHECKERS, default='standard')
    grader = models.CharField(max_length=30, verbose_name=_('Grader'), choices=GRADERS, default='standard')
    unicode = models.BooleanField(verbose_name=_('enable unicode'), null=True, blank=True)
    nobigmath = models.BooleanField(verbose_name=_('disable bigInteger / bigDecimal'), null=True, blank=True)
    checker_args = models.TextField(verbose_name=_('checker arguments'), blank=True,
                                    help_text=_('Checker arguments as a JSON object.'))

    custom_checker = models.FileField(verbose_name=_('custom checker file'), storage=problem_data_storage,
                                      null=True,
                                      blank=True,
                                      upload_to=problem_directory_file,
                                      validators=[FileExtensionValidator(
                                          allowed_extensions=['cpp', 'pas', 'java'],
                                      )])

    custom_grader = models.FileField(verbose_name=_('custom grader file'), storage=problem_data_storage,
                                     null=True,
                                     blank=True,
                                     upload_to=problem_directory_file,
                                     validators=[FileExtensionValidator(allowed_extensions=['cpp'])])

    custom_header = models.FileField(verbose_name=_('custom header file'), storage=problem_data_storage,
                                     null=True,
                                     blank=True,
                                     upload_to=problem_directory_file,
                                     validators=[FileExtensionValidator(allowed_extensions=['h'])])

    grader_args = models.TextField(verbose_name=_('grader arguments'), blank=True,
                                   help_text=_('grader arguments as a JSON object'))
    zipfile_size = models.BigIntegerField(verbose_name=_('test data storage size'), default=0,
                                          help_text=_('Size of the test data zip file in bytes.'))
    submission_files_size = models.BigIntegerField(verbose_name=_('submission files storage size'), default=0,
                                                   help_text=_('Size of all submission files in bytes.'))

    def has_yml(self):
        return problem_data_storage.exists('%s/init.yml' % self.problem.code)

    def update_zipfile_size(self):
        """Update the zipfile_size field based on the actual file size."""
        if self.zipfile:
            try:
                self.zipfile_size = self.zipfile.size
            except (OSError, IOError):
                # If file doesn't exist or can't be accessed, set size to 0
                self.zipfile_size = 0
        else:
            self.zipfile_size = 0

    def update_submission_files_size(self):
        """Calculate total size of all submission files for this problem."""
        from django.conf import settings
        from django.core.files.storage import default_storage
        
        total_size = 0
        submission_dir = os.path.join(settings.SUBMISSION_FILE_UPLOAD_MEDIA_DIR, self.problem.code)
        
        try:
            # Check if the directory exists
            if default_storage.exists(submission_dir):
                # Walk through all subdirectories and files
                dirs, files = default_storage.listdir(submission_dir)
                
                # Process files in root directory
                for filename in files:
                    file_path = os.path.join(submission_dir, filename)
                    try:
                        total_size += default_storage.size(file_path)
                    except (OSError, IOError):
                        pass
                
                # Process subdirectories (user_id directories)
                for user_dir in dirs:
                    user_path = os.path.join(submission_dir, user_dir)
                    try:
                        _, user_files = default_storage.listdir(user_path)
                        for filename in user_files:
                            file_path = os.path.join(user_path, filename)
                            try:
                                total_size += default_storage.size(file_path)
                            except (OSError, IOError):
                                pass
                    except (OSError, IOError):
                        pass
        except (OSError, IOError):
            pass
        
        self.submission_files_size = total_size

    def save(self, *args, **kwargs):
        # Update zipfile size before saving
        self.update_zipfile_size()
        super(ProblemData, self).save(*args, **kwargs)
        
        # Invalidate organization storage cache when size changes
        if self.problem.organization:
            from django.core.cache import cache
            cache_key = f'org_storage_total_{self.problem.organization.id}'
            cache.delete(cache_key)

    def _update_code(self, original, new):
        try:
            problem_data_storage.rename(original, new)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        if self.zipfile:
            self.zipfile.name = _problem_directory_file(new, self.zipfile.name)
        if self.generator:
            self.generator.name = _problem_directory_file(new, self.generator.name)
        if self.custom_checker:
            self.custom_checker.name = _problem_directory_file(new, self.custom_checker.name)
        if self.custom_grader:
            self.custom_grader.name = _problem_directory_file(new, self.custom_grader.name)
        if self.custom_header:
            self.custom_header.name = _problem_directory_file(new, self.custom_header.name)
        self.save()
    _update_code.alters_data = True


class ProblemTestCase(models.Model):
    dataset = models.ForeignKey('Problem', verbose_name=_('problem data set'), related_name='cases',
                                on_delete=models.CASCADE)
    order = models.IntegerField(verbose_name=_('case position'))
    type = models.CharField(max_length=1, verbose_name=_('case type'),
                            choices=(('C', _('Normal case')),
                                     ('S', _('Batch start')),
                                     ('E', _('Batch end'))),
                            default='C')
    input_file = models.CharField(max_length=100, verbose_name=_('input file name'), blank=True)
    output_file = models.CharField(max_length=100, verbose_name=_('output file name'), blank=True)
    generator_args = models.TextField(verbose_name=_('generator arguments'), blank=True)
    points = models.IntegerField(verbose_name=_('point value'), blank=True, null=True)
    is_pretest = models.BooleanField(verbose_name=_('case is pretest?'))
    output_prefix = models.IntegerField(verbose_name=_('output prefix length'), blank=True, null=True)
    output_limit = models.IntegerField(verbose_name=_('output limit length'), blank=True, null=True)
    checker = models.CharField(max_length=10, verbose_name=_('checker'), choices=CHECKERS, blank=True)
    checker_args = models.TextField(verbose_name=_('checker arguments'), blank=True,
                                    help_text=_('Checker arguments as a JSON object.'))
