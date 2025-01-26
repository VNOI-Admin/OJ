import os
import zipfile

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import translation
from lxml import etree as ET

from judge.models import Language, Problem, Profile, Submission, SubmissionSource


class Command(BaseCommand):
    help = 'submit solutions from Polygon package'

    def add_arguments(self, parser):
        parser.add_argument('package', help='path to package in zip format')
        parser.add_argument('code', help='problem code')
        parser.add_argument('submitter', help='username of submitter')

    def handle(self, *args, **options):
        # Force using English
        translation.activate('en')

        problem = Problem.objects.get(code=options['code'])
        submitter = Profile.objects.get(user__username=options['submitter'])

        package = zipfile.ZipFile(options['package'], 'r')
        if 'problem.xml' not in package.namelist():
            raise CommandError('problem.xml not found')

        root = ET.fromstring(package.read('problem.xml'))
        solutions = root.find('.//solutions')
        for solution in solutions.getchildren():
            source = solution.find('source')
            source_path = source.get('path')
            source_lang = source.get('type')

            comments = [os.path.basename(source_path), f'overall: {solution.get("tag")}']

            extra_tags = solution.find('extra-tags')
            if extra_tags is not None:
                for extra_tag in extra_tags.getchildren():
                    group = extra_tag.get('group')
                    tag = extra_tag.get('tag')
                    if group is not None:
                        comments.append(f'group {group}: {tag}')

            if source_lang.startswith('cpp'):
                header = '/*\n' + '\n'.join(comments) + '\n*/\n\n'
                source_code = header + package.read(source_path).decode('utf-8')
                language = Language.objects.get(key='CPP20')
            elif source_lang.startswith('java'):
                header = '/*\n' + '\n'.join(comments) + '\n*/\n\n'
                source_code = header + package.read(source_path).decode('utf-8')
                language = Language.objects.get(key='JAVA')
            elif source_lang.startswith('pas'):
                header = '{\n' + '\n'.join(comments) + '\n}\n\n'
                source_code = header + package.read(source_path).decode('utf-8')
                language = Language.objects.get(key='PAS')
            elif source_lang.startswith('python'):
                header = '"""\n' + '\n'.join(comments) + '\n"""\n\n'
                source_code = header + package.read(source_path).decode('utf-8')
                if source_lang == 'python.pypy2':
                    language = Language.objects.get(key='PYPY')
                elif source_lang.startswith('python.pypy3'):
                    language = Language.objects.get(key='PYPY3')
                elif source_lang == 'python.2':
                    language = Language.objects.get(key='PY2')
                else:
                    language = Language.objects.get(key='PY3')
            elif source_lang.startswith('kotlin'):
                header = '/*\n' + '\n'.join(comments) + '\n*/\n\n'
                source_code = header + package.read(source_path).decode('utf-8')
                language = Language.objects.get(key='KOTLIN')
            elif source_lang == 'go':
                header = '/*\n' + '\n'.join(comments) + '\n*/\n\n'
                source_code = header + package.read(source_path).decode('utf-8')
                language = Language.objects.get(key='GO')
            elif source_lang == 'rust':
                header = '/*\n' + '\n'.join(comments) + '\n*/\n\n'
                source_code = header + package.read(source_path).decode('utf-8')
                language = Language.objects.get(key='RUST')
            else:
                print('Unsupported language', source_lang)
                continue

            with transaction.atomic():
                submission = Submission(user=submitter, problem=problem, language=language)
                submission.save()
                source = SubmissionSource(submission=submission, source=source_code)
                source.save()

            submission.source = source
            submission.judge(force_judge=True)
