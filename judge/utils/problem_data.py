import json
import os
import re

import yaml
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils.translation import gettext as _


if os.altsep:
    def split_path_first(path, repath=re.compile('[%s]' % re.escape(os.sep + os.altsep))):
        return repath.split(path, 1)
else:
    def split_path_first(path):
        return path.split(os.sep, 1)


class ProblemDataStorage(FileSystemStorage):
    def __init__(self):
        super(ProblemDataStorage, self).__init__(settings.DMOJ_PROBLEM_DATA_ROOT)

    def url(self, name):
        path = split_path_first(name)
        if len(path) != 2:
            raise ValueError('This file is not accessible via a URL.')
        return reverse('problem_data_file', args=path)

    def _save(self, name, content):
        if self.exists(name):
            self.delete(name)
        return super(ProblemDataStorage, self)._save(name, content)

    def get_available_name(self, name, max_length=None):
        return name

    def rename(self, old, new):
        return os.rename(self.path(old), self.path(new))


class ProblemDataError(Exception):
    def __init__(self, message):
        super(ProblemDataError, self).__init__(message)
        self.message = message


class ProblemDataCompiler(object):
    def __init__(self, problem, data, cases, files):
        self.problem = problem
        self.data = data
        self.cases = cases
        self.files = files

        self.generator = data.generator

    def make_init(self):
        cases = []
        batch = None

        def end_batch():
            if not batch['batched']:
                raise ProblemDataError(_('Empty batches not allowed.'))
            cases.append(batch)

        def make_checker(case):
            if (case.checker == 'bridged'):
                custom_checker_path = split_path_first(case.custom_checker.name)
                if len(custom_checker_path) != 2:
                    raise ProblemDataError(_('How did you corrupt the custom checker path?'))
                try:
                    checker_ext = custom_checker_path[1].split('.')[-1]
                except Exception as e:
                    raise ProblemDataError(e)

                # Python checker doesn't need to use bridged
                # so we return the name dirrectly
                if checker_ext == 'py':
                    return custom_checker_path[1]

                if checker_ext != 'cpp':
                    raise ProblemDataError(_("Why don't you use a cpp/py checker?"))
                # the cpp checker will be handled
                # right below here, outside of this scope

            if case.checker_args:
                return {
                    'name': case.checker,
                    'args': json.loads(case.checker_args),
                }
            return case.checker

        def get_file_name_and_ext(file):
            file_path = split_path_first(file)
            if len(file_path) != 2:
                raise ProblemDataError(_('How did you corrupt the custom grader path?'))
            try:
                file_ext = file_path[1].split('.')[-1]
            except Exception as e:
                raise ProblemDataError(e)
            return file_path[1], file_ext

        def make_grader(init, case):
            # We don't need to do anything if it is standard grader
            if case.grader == 'standard':
                return
            if case.grader == 'output_only':
                init['output_only'] = True
                return
            grader_args = {}
            if case.grader_args:
                grader_args = json.loads(case.grader_args)

            if case.grader == 'interactive':
                file_name, file_ext = get_file_name_and_ext(case.custom_grader.name)
                if file_ext != 'cpp':
                    raise ProblemDataError(_("Only accept `.cpp` interactor"))

                init['interactive'] = {
                    'files': file_name,
                    'type': 'testlib',  # Assume that we only use testlib interactor
                    'lang': 'CPP17',
                }
                return

            if case.grader == 'signature':
                file_name, file_ext = get_file_name_and_ext(case.custom_grader.name)
                if file_ext != 'cpp':
                    raise ProblemDataError(_("Only accept `.cpp` entry"))
                header_name, file_ext = get_file_name_and_ext(case.custom_header.name)
                if file_ext != 'h':
                    raise ProblemDataError(_("Only accept `.h` header"))
                init['signature_grader'] = {
                    'entry': file_name,
                    'header': header_name,
                }
                # Most of the time, we don't want user to write their own main function
                # However, some problem require user to write the main function themself
                # *cough* *cough* olympic super cup 2020 MXOR *cough* *cough*
                # Check: https://github.com/DMOJ/judge-server/issues/730
                if grader_args.get('allow_main', False):
                    init['signature_grader']['allow_main'] = True
                return

            if case.grader == 'custom_judge':
                file_name, file_ext = get_file_name_and_ext(case.custom_grader.name)
                if file_ext != 'py':
                    raise ProblemDataError(_("Only accept `.py` custom judge"))
                init['custom_judge'] = file_name
                return

        for i, case in enumerate(self.cases, 1):
            if case.type == 'C':
                data = {}
                if batch:
                    case.points = None
                    case.is_pretest = batch['is_pretest']
                else:
                    if case.points is None:
                        raise ProblemDataError(_('Points must be defined for non-batch case #%d.') % i)
                    data['is_pretest'] = case.is_pretest

                if not self.generator:
                    if case.input_file not in self.files:
                        raise ProblemDataError(_('Input file for case %d does not exist: %s') %
                                               (i, case.input_file))
                    if case.output_file not in self.files:
                        raise ProblemDataError(_('Output file for case %d does not exist: %s') %
                                               (i, case.output_file))

                if case.input_file:
                    data['in'] = case.input_file
                if case.output_file:
                    data['out'] = case.output_file
                if case.points is not None:
                    data['points'] = case.points
                if case.generator_args:
                    data['generator_args'] = case.generator_args.splitlines()
                if case.output_limit is not None:
                    data['output_limit_length'] = case.output_limit
                if case.output_prefix is not None:
                    data['output_prefix_length'] = case.output_prefix
                if case.checker:
                    data['checker'] = make_checker(case)
                else:
                    case.checker_args = ''
                case.save(update_fields=('checker_args', 'is_pretest'))
                (batch['batched'] if batch else cases).append(data)
            elif case.type == 'S':
                if batch:
                    end_batch()
                if case.points is None:
                    raise ProblemDataError(_('Batch start case #%d requires points.') % i)
                batch = {
                    'points': case.points,
                    'batched': [],
                    'is_pretest': case.is_pretest,
                }
                if case.generator_args:
                    batch['generator_args'] = case.generator_args.splitlines()
                if case.output_limit is not None:
                    batch['output_limit_length'] = case.output_limit
                if case.output_prefix is not None:
                    batch['output_prefix_length'] = case.output_prefix
                if case.checker:
                    batch['checker'] = make_checker(case)
                else:
                    case.checker_args = ''
                case.input_file = ''
                case.output_file = ''
                case.save(update_fields=('checker_args', 'input_file', 'output_file'))
            elif case.type == 'E':
                if not batch:
                    raise ProblemDataError(_('Attempt to end batch outside of one in case #%d') % i)
                case.is_pretest = batch['is_pretest']
                case.input_file = ''
                case.output_file = ''
                case.generator_args = ''
                case.checker = ''
                case.checker_args = ''
                case.save()
                end_batch()
                batch = None
        if batch:
            end_batch()

        init = {}

        if self.data.zipfile:
            zippath = split_path_first(self.data.zipfile.name)
            if len(zippath) != 2:
                raise ProblemDataError(_('How did you corrupt the zip path?'))
            init['archive'] = zippath[1]

        if self.generator:
            generator_path = split_path_first(self.generator.name)
            if len(generator_path) != 2:
                raise ProblemDataError(_('How did you corrupt the generator path?'))
            init['generator'] = generator_path[1]

        pretests = [case for case in cases if case['is_pretest']]
        for case in cases:
            del case['is_pretest']
        if pretests:
            init['pretest_test_cases'] = pretests
        if cases:
            init['test_cases'] = cases
        if self.data.output_limit is not None:
            init['output_limit_length'] = self.data.output_limit
        if self.data.output_prefix is not None:
            init['output_prefix_length'] = self.data.output_prefix
        if self.data.checker:
            init['checker'] = make_checker(self.data)
        else:
            self.data.checker_args = ''
        if self.data.grader:
            make_grader(init, self.data)
        return init

    def compile(self):
        from judge.models import problem_data_storage

        yml_file = '%s/init.yml' % self.problem.code
        try:
            init = yaml.safe_dump(self.make_init())
        except ProblemDataError as e:
            self.data.feedback = e.message
            self.data.save()
            problem_data_storage.delete(yml_file)
        else:
            self.data.feedback = ''
            self.data.save()
            if init:
                problem_data_storage.save(yml_file, ContentFile(init))
            else:
                # Don't write empty init.yml since we should be looking in manually managed
                # judge-server#670 will not update cache on empty init.yml,
                # but will do so if there is no init.yml, so we delete the init.yml
                problem_data_storage.delete(yml_file)

    @classmethod
    def generate(cls, *args, **kwargs):
        self = cls(*args, **kwargs)
        self.compile()
