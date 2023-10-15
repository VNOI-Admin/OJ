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

    def has_yml(self):
        return problem_data_storage.exists('%s/init.yml' % self.problem.code)

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
