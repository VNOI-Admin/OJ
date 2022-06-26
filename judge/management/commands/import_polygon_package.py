import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from operator import itemgetter

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse
from django.utils import translation
from lxml import etree as ET

from judge.models import Language, Problem, ProblemData, ProblemGroup, ProblemTestCase, ProblemTranslation, ProblemType
from judge.utils.problem_data import ProblemDataCompiler
from judge.views.widgets import django_uploader

PANDOC_FILTER = """
local List = require 'pandoc.List'

function normalize_quote(text)
    -- These four quotes are disallowed characters.
    -- See DMOJ_PROBLEM_STATEMENT_DISALLOWED_CHARACTERS
    text = text:gsub('\\u{2018}', "'") -- left single quote
    text = text:gsub('\\u{2019}', "'") -- right single quote
    text = text:gsub('\\u{201C}', '"') -- left double quote
    text = text:gsub('\\u{201D}', '"') -- right double quote
    return text
end

function Math(m)
    -- Fix math delimiters
    local delimiter = m.mathtype == 'InlineMath' and '~' or '$$'
    return pandoc.RawInline('markdown', delimiter .. m.text .. delimiter)
end

function Image(el)
    -- And line breaks before the image
    return {pandoc.RawInline('markdown', '\\n\\n'), el}
end

function Code(el)
    -- Normalize quotes
    el.text = normalize_quote(el.text)
    return el
end

function CodeBlock(el)
    -- Normalize quotes
    el.text = normalize_quote(el.text)
    return el
end

function Quoted(el)
    -- Normalize quotes
    local quote = el.quotetype == 'SingleQuote' and "'" or '"'
    local inlines = el.content
    table.insert(inlines, 1, quote)
    table.insert(inlines, quote)
    return inlines
end

function Str(el)
    -- en dash and em dash would still show up correctly if we don't escape
    -- them, but they would be hardly noticeable while editing.
    el.text = el.text:gsub('\\u{2013}', '&ndash;')
    el.text = el.text:gsub('\\u{2014}', '&mdash;')

    -- Normalize quotes
    el.text = normalize_quote(el.text)

    return el
end

function Div(el)
    -- Currently only used for <center>
    -- FIXME: What about other classes?
    local res = List:new{}
    table.insert(res, pandoc.RawBlock('markdown', '<' .. el.classes[1] .. '>'))
    for _, block in ipairs(el.content) do
        table.insert(res, block)
    end
    table.insert(res, pandoc.RawBlock('markdown', '</' .. el.classes[1] .. '>'))
    return res
end
"""


def parse_checker(problem_meta, root, package):
    checker = root.find('.//checker')
    if checker is None:
        raise CommandError('checker not found')

    if checker.get('type') != 'testlib':
        raise CommandError('not a testlib checker. how possible?')

    print('Use standard grader')
    problem_meta['grader'] = 'standard'

    checker_name = checker.get('name')
    if checker_name is None:
        problem_meta['checker'] = 'bridged'
    else:
        if checker_name in ['std::hcmp.cpp', 'std::ncmp.cpp', 'std::wcmp.cpp']:
            problem_meta['checker'] = 'standard'
            print('Use standard checker')
        elif checker_name in ['std::rcmp4.cpp', 'std::rcmp6.cpp', 'std::rcmp9.cpp']:
            problem_meta['checker'] = 'floats'
            problem_meta['checker_args'] = {'precision': int(checker_name[9])}
            print(f'Use floats checker with precision {problem_meta["checker_args"]["precision"]}')
        elif checker_name == 'std::fcmp.cpp':
            problem_meta['checker'] = 'identical'
            print('Use identical checker')
        elif checker_name == 'std::lcmp.cpp':
            problem_meta['checker'] = 'linecount'
            print('Use linecount checker')
        else:
            problem_meta['checker'] = 'bridged'

    if problem_meta['checker'] == 'bridged':
        print('Use custom checker')

        source = checker.find('source')
        if source is None:
            raise CommandError('checker source not found. how possible?')

        # TODO: support more checkers?
        path = source.get('path')
        if not path.lower().endswith('.cpp'):
            raise CommandError('checker must use C++')

        problem_meta['checker_args'] = {
            'files': 'checker.cpp',
            'lang': 'CPP17',
            'type': 'testlib',
        }

        problem_meta['custom_checker'] = os.path.join(problem_meta['tmp_dir'].name, 'checker.cpp')
        with open(problem_meta['custom_checker'], 'wb') as f:
            f.write(package.read(path))


def parse_tests(problem_meta, root, package):
    testset = root.find('.//testset[@name="tests"]')
    if testset is None:
        raise CommandError('testset tests not found')

    if len(testset.find('tests').getchildren()) == 0:
        raise CommandError('no testcases found')

    # Polygon specifies the time limit in ms and memory limit in bytes,
    # while DMOJ uses seconds and kilobytes.
    problem_meta['time_limit'] = float(testset.find('time-limit').text) / 1000
    problem_meta['memory_limit'] = int(testset.find('memory-limit').text) // 1024

    if hasattr(settings, 'DMOJ_PROBLEM_MIN_MEMORY_LIMIT'):
        problem_meta['memory_limit'] = max(problem_meta['memory_limit'], settings.DMOJ_PROBLEM_MIN_MEMORY_LIMIT)
    if hasattr(settings, 'DMOJ_PROBLEM_MAX_MEMORY_LIMIT'):
        problem_meta['memory_limit'] = min(problem_meta['memory_limit'], settings.DMOJ_PROBLEM_MAX_MEMORY_LIMIT)

    print(f'Time limit: {problem_meta["time_limit"]}s')
    print(f'Memory limit: {problem_meta["memory_limit"] // 1024}MB')

    problem_meta['cases'] = []
    problem_meta['batches'] = {}
    problem_meta['zipfile'] = os.path.join(problem_meta['tmp_dir'].name, 'tests.zip')
    tests_zip = zipfile.ZipFile(problem_meta['zipfile'], 'w')

    input_path_pattern = testset.find('input-path-pattern').text
    answer_path_pattern = testset.find('answer-path-pattern').text
    total_points = 0

    groups = testset.find('groups')
    if groups is not None:
        for group in groups.getchildren():
            points_policy = group.get('points-policy')
            if points_policy == 'complete-group':
                points = int(float(group.get('points', 0)))
                problem_meta['batches'][group.get('name')] = {'points': points, 'cases': []}
                total_points += points

    for i, test in enumerate(testset.find('tests').getchildren(), start=1):
        input_path = input_path_pattern % i
        answer_path = answer_path_pattern % i
        points = int(float(test.get('points', 0)))
        total_points += points

        tests_zip.writestr(f'{i:02d}.inp', package.read(input_path))
        tests_zip.writestr(f'{i:02d}.out', package.read(answer_path))

        group = test.get('group', '')
        if group in problem_meta['batches']:
            problem_meta['batches'][group]['cases'].append({
                'input_file': f'{i:02d}.inp',
                'output_file': f'{i:02d}.out',
            })
        else:
            problem_meta['cases'].append({
                'input_file': f'{i:02d}.inp',
                'output_file': f'{i:02d}.out',
                'points': points,
            })

    tests_zip.close()

    print(f'Found {len(testset.find("tests").getchildren())} testcases!')

    if total_points == 0:
        print('Total points is zero. Set partial to False')
        problem_meta['partial'] = False
    else:
        print('Total points is non-zero. Set partial to True')
        problem_meta['partial'] = True

    problem_meta['grader_args'] = {}
    judging = root.find('.//judging')
    if judging is not None:
        io_input_file = judging.get('input-file', '')
        io_output_file = judging.get('output-file', '')

        if io_input_file != '' and io_output_file != '':
            print('Use File IO')
            print('Input file:', io_input_file)
            print('Output file:', io_output_file)
            problem_meta['grader_args']['io_method'] = 'file'
            problem_meta['grader_args']['io_input_file'] = io_input_file
            problem_meta['grader_args']['io_output_file'] = io_output_file


def pandoc_tex_to_markdown(tex):
    tmp_dir = tempfile.TemporaryDirectory()
    with open(os.path.join(tmp_dir.name, 'temp.tex'), 'w') as f:
        f.write(tex)
    with open(os.path.join(tmp_dir.name, 'filter.lua'), 'w') as f:
        f.write(PANDOC_FILTER)
    subprocess.run(['pandoc', '--lua-filter=filter.lua', '-t', 'gfm', '-o', 'temp.md', 'temp.tex'], cwd=tmp_dir.name)
    with open(os.path.join(tmp_dir.name, 'temp.md'), 'r') as f:
        md = f.read()
    tmp_dir.cleanup()

    return md


def parse_statements(problem_meta, root, package):
    image_cache = {}

    def save_image(image_path):
        norm_path = os.path.normpath(os.path.join(statement_folder, image_path))
        sha1 = hashlib.sha1()
        sha1.update(package.open(norm_path, 'r').read())
        sha1 = sha1.hexdigest()

        if sha1 not in image_cache:
            image = File(
                file=package.open(norm_path, 'r'),
                name=os.path.basename(image_path),
            )
            data = json.loads(django_uploader(image))
            image_cache[sha1] = data['link']

        return image_cache[sha1]

    def parse_problem_properties(problem_properties):
        description = ''

        # Legend
        description += pandoc_tex_to_markdown(problem_properties['legend'])

        # Input
        description += '\n## Input\n\n'
        description += pandoc_tex_to_markdown(problem_properties['input'])

        # Output
        description += '\n## Output\n\n'
        description += pandoc_tex_to_markdown(problem_properties['output'])

        # Scoring
        if problem_properties['scoring'] is not None:
            description += '\n## Scoring\n\n'
            description += pandoc_tex_to_markdown(problem_properties['scoring'])

        # Sample tests
        for i, sample in enumerate(problem_properties['sampleTests'], start=1):
            description += f'\n## Sample Input {i}\n\n'
            description += '```\n' + sample['input'].strip() + '\n```\n'
            description += f'\n## Sample Output {i}\n\n'
            description += '```\n' + sample['output'].strip() + '\n```\n'

        # Notes
        if problem_properties['notes'] != '':
            description += '\n## Notes\n\n'
            description += pandoc_tex_to_markdown(problem_properties['notes'])

        # Images
        for image_path in set(re.findall(r'!\[image\]\((.+?)\)', description)):
            description = description.replace(
                f'![image]({image_path})',
                f'![image]({save_image(image_path)})',
            )

        for img_tag in set(re.findall(r'<\s*img[^>]*>', description)):
            image_path = re.search(r'<\s*img[^>]+src\s*=\s*(["\'])(.*?)\1[^>]*>', description).group(2)
            description = description.replace(
                img_tag,
                img_tag.replace(image_path, save_image(image_path)),
            )

        return description

    def input_choice(prompt, choices):
        while True:
            choice = input(prompt)
            if choice in choices:
                return choice
            else:
                print('Invalid choice')

    statements = root.findall('.//statement[@type="application/x-tex"]')
    if len(statements) == 0:
        print('Statement not found! Would you like to skip statement (y/n)? ', end='', flush=True)
        if input().lower() in ['y', 'yes']:
            problem_meta['name'] = ''
            problem_meta['description'] = ''
            problem_meta['translations'] = []
            return

        raise CommandError('statement not found')

    translations = []
    for statement in statements:
        language = statement.get('language', 'unknown')
        statement_folder = os.path.dirname(statement.get('path'))
        problem_properties_path = os.path.join(statement_folder, 'problem-properties.json')
        if problem_properties_path not in package.namelist():
            raise CommandError(f'problem-properties.json not found at path {problem_properties_path}')

        problem_properties = json.loads(package.read(problem_properties_path).decode('utf-8'))

        print(f'Converting statement in language {language} to Markdown')
        description = parse_problem_properties(problem_properties)
        translations.append({
            'language': language,
            'description': description,
        })

    if len(translations) > 1:
        languages = [t['language'] for t in translations]
        print('Multilingual statements found:', languages)
        main_language = input_choice('Please select one as the main statement: ', languages)
    else:
        main_language = translations[0]['language']

    problem_meta['translations'] = []

    for t in translations:
        language = t['language']
        description = t['description']
        name_element = root.find(f'.//name[@language="{language}"]')
        name = name_element.get('value') if name_element is not None else ''

        if language == main_language:
            problem_meta['name'] = name
            problem_meta['description'] = description
        else:
            choices = list(map(itemgetter(0), settings.LANGUAGES))
            site_language = input_choice(
                f'Please select corresponding site language for {language} '
                f'(available options are {", ".join(choices)}): ',
                choices,
            )
            problem_meta['translations'].append({
                'language': site_language,
                'name': name,
                'description': description,
            })


@transaction.atomic
def create_problem(problem_meta):
    print('Creating problem in database')
    problem = Problem(
        code=problem_meta['code'],
        name=problem_meta['name'],
        time_limit=problem_meta['time_limit'],
        memory_limit=problem_meta['memory_limit'],
        description=problem_meta['description'],
        partial=problem_meta['partial'],
        group=ProblemGroup.objects.order_by('id').first(),  # Uncategorized
        points=0.0,
    )
    problem.save()
    problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
    problem.types.set([ProblemType.objects.order_by('id').first()])  # Uncategorized
    problem.save()

    for tran in problem_meta['translations']:
        ProblemTranslation(
            problem=problem,
            language=tran['language'],
            name=tran['name'],
            description=tran['description'],
        ).save()

    with open(problem_meta['zipfile'], 'rb') as f:
        problem_data = ProblemData(
            problem=problem,
            zipfile=File(f),
            grader=problem_meta['grader'],
            checker=problem_meta['checker'],
            grader_args=json.dumps(problem_meta['grader_args']),
        )
        problem_data.save()

    if problem_meta['checker'] == 'bridged':
        with open(problem_meta['custom_checker'], 'rb') as f:
            problem_data.custom_checker = File(f)
            problem_data.save()

    if 'checker_args' in problem_meta:
        problem_data.checker_args = json.dumps(problem_meta['checker_args'])
        problem_data.save()

    order = 0

    for batch in problem_meta['batches'].values():
        if len(batch['cases']) == 0:
            continue

        order += 1
        start_batch = ProblemTestCase(dataset=problem, order=order, type='S', points=batch['points'], is_pretest=False)
        start_batch.save()

        for case_data in batch['cases']:
            order += 1
            case = ProblemTestCase(
                dataset=problem,
                order=order,
                type='C',
                input_file=case_data['input_file'],
                output_file=case_data['output_file'],
                is_pretest=False,
            )
            case.save()

        order += 1
        end_batch = ProblemTestCase(dataset=problem, order=order, type='E', is_pretest=False)
        end_batch.save()

    for case_data in problem_meta['cases']:
        order += 1
        case = ProblemTestCase(
            dataset=problem,
            order=order,
            type='C',
            input_file=case_data['input_file'],
            output_file=case_data['output_file'],
            points=case_data['points'],
            is_pretest=False,
        )
        case.save()

    print('Generating init.yml')
    ProblemDataCompiler.generate(
        problem=problem,
        data=problem_data,
        cases=problem.cases.order_by('order'),
        files=zipfile.ZipFile(problem_data.zipfile.path).namelist(),
    )


class Command(BaseCommand):
    help = 'import Codeforces Polygon full package'

    def add_arguments(self, parser):
        parser.add_argument('package', help='path to package in zip format')
        parser.add_argument('code', help='problem code')

    def handle(self, *args, **options):
        # Force using English
        translation.activate('en')

        # Check if pandoc is available
        if not shutil.which('pandoc'):
            raise CommandError('pandoc not installed')

        # Let's validate the problem code right now.
        # We don't want to have done everything and still fail because
        # of invalid problem code.
        problem_code = options['code']
        Problem._meta.get_field('code').run_validators(problem_code)
        if Problem.objects.filter(code=problem_code).exists():
            raise CommandError(f'problem with code {problem_code} already exists')

        package = zipfile.ZipFile(options['package'], 'r')
        if 'problem.xml' not in package.namelist():
            raise CommandError('problem.xml not found')

        root = ET.fromstring(package.read('problem.xml'))

        # A dictionary to hold all problem information.
        problem_meta = {}
        problem_meta['code'] = problem_code
        problem_meta['tmp_dir'] = tempfile.TemporaryDirectory()

        try:
            parse_checker(problem_meta, root, package)
            parse_tests(problem_meta, root, package)
            parse_statements(problem_meta, root, package)
            create_problem(problem_meta)
        except Exception:
            raise
        finally:
            problem_meta['tmp_dir'].cleanup()

        problem_url = 'https://' + Site.objects.first().domain + reverse('problem_detail', args=[problem_code])
        print(f'Imported successfully. View problem at {problem_url}')
