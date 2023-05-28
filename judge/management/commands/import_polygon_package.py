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
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone, translation
from lxml import etree as ET

from judge.models import Language, Problem, ProblemData, ProblemGroup, ProblemTestCase, ProblemTranslation, \
    ProblemType, Profile, Solution
from judge.utils.problem_data import ProblemDataCompiler
from judge.views.widgets import django_uploader

PANDOC_FILTER = r"""
local function normalize_quote(text)
    -- These four quotes are disallowed characters.
    -- See DMOJ_PROBLEM_STATEMENT_DISALLOWED_CHARACTERS
    text = text:gsub('\u{2018}', "'") -- left single quote
    text = text:gsub('\u{2019}', "'") -- right single quote
    text = text:gsub('\u{201C}', '"') -- left double quote
    text = text:gsub('\u{201D}', '"') -- right double quote
    return text
end

local function escape_html_content(text)
    -- Escape HTML/Markdown/MathJax syntax characters
    text = text:gsub('&', '&amp;') -- must be first
    text = text:gsub('<', "&lt;")
    text = text:gsub('>', "&gt;")
    text = text:gsub('*', '\\*')
    text = text:gsub('_', '\\_')
    text = text:gsub('%$', '<span>%$</span>')
    text = text:gsub('~', '<span>~</span>')
    return text
end

function Math(m)
    -- Fix math delimiters
    local delimiter = m.mathtype == 'InlineMath' and '~' or '$$'
    return pandoc.RawInline('html', delimiter .. m.text .. delimiter)
end

function Image(el)
    -- And blank lines before and after the image for caption to work
    return {pandoc.RawInline('markdown', '\n\n'), el, pandoc.RawInline('markdown', '\n\n')}
end

function Code(el)
    -- Normalize quotes and render similar to Codeforces
    local text = normalize_quote(el.text)
    text = escape_html_content(text)
    return pandoc.RawInline('html', '<span style="font-family: courier new,monospace;">' .. text .. '</span>')
end

function CodeBlock(el)
    -- Normalize quotes
    el.text = normalize_quote(el.text)

    -- Set language to empty string if it's nil
    -- This is a hack to force backtick code blocks instead of indented code blocks
    -- See https://github.com/jgm/pandoc/issues/7033
    if el.classes[1] == nil then
        el.classes[1] = ''
    end

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
    -- Normalize quotes
    el.text = normalize_quote(el.text)

    -- en dash/em dash/non-breaking space would still show up correctly if we don't escape them,
    -- but they would be hardly noticeable while editing.
    local res = {}
    local part = ''
    for c in el.text:gmatch(utf8.charpattern) do
        if c == '\u{2013}' then
            -- en dash
            if part ~= '' then
                table.insert(res, pandoc.Str(part))
                part = ''
            end
            table.insert(res, pandoc.RawInline('html', '&ndash;'))
        elseif c == '\u{2014}' then
            -- em dash
            if part ~= '' then
                table.insert(res, pandoc.Str(part))
                part = ''
            end
            table.insert(res, pandoc.RawInline('html', '&mdash;'))
        elseif c == '\u{00A0}' then
            -- Non-breaking space
            if part ~= '' then
                table.insert(res, pandoc.Str(part))
                part = ''
            end
            table.insert(res, pandoc.RawInline('html', '&nbsp;'))
        else
            part = part .. c
        end
    end
    if part ~= '' then
        table.insert(res, pandoc.Str(part))
    end

    return res
end

function Div(el)
    if el.classes[1] == 'center' then
        local res = {}
        table.insert(res, pandoc.RawBlock('markdown', '<' .. el.classes[1] .. '>'))
        for _, block in ipairs(el.content) do
            table.insert(res, block)
        end
        table.insert(res, pandoc.RawBlock('markdown', '</' .. el.classes[1] .. '>'))
        return res

    elseif el.classes[1] == 'epigraph' then
        local filter = {
            Math = Math,
            Code = Code,
            Quoted = Quoted,
            Str = Str,
            Para = function (s)
                return pandoc.Plain(s.content)
            end,
            Span = function (s)
                return s.content
            end
        }

        function renderHTML(el)
            local doc = pandoc.Pandoc({el})
            local rendered = pandoc.write(doc:walk(filter), 'html')
            return pandoc.RawBlock('markdown', rendered)
        end

        local res = {}
        table.insert(res, pandoc.RawBlock('markdown', '<div style="margin-left: 67%;">'))
        if el.content[1] then
            table.insert(res, renderHTML(el.content[1]))
        end
        table.insert(res, pandoc.RawBlock('markdown', '<div style="border-top: 1px solid #888;"></div>'))
        if el.content[2] then
            table.insert(res, renderHTML(el.content[2]))
        end
        table.insert(res, pandoc.RawBlock('markdown', '</div>'))
        return res
    end

    return nil
end
"""


# Polygon uses some custom macros: https://polygon.codeforces.com/docs/statements-tex-manual
# For example, \bf is deprecated in modern LaTeX, but Polygon treats it the same as \textbf
# and recommends writing \bf{...} instead of \textbf{...} for brevity.
# Similar for \it, \tt, \t
# We just redefine them to their modern counterparts.
# Note that this would break {\bf abcd}, but AFAIK Polygon never recommends that so it's fine.
TEX_MACROS = r"""
\renewcommand{\bf}{\textbf}
\renewcommand{\it}{\textit}
\renewcommand{\tt}{\texttt}
\renewcommand{\t}{\texttt}
"""


def pandoc_tex_to_markdown(tex):
    tex = TEX_MACROS + tex
    with tempfile.TemporaryDirectory() as tmp_dir:
        with open(os.path.join(tmp_dir, 'temp.tex'), 'w', encoding='utf-8') as f:
            f.write(tex)

        with open(os.path.join(tmp_dir, 'filter.lua'), 'w', encoding='utf-8') as f:
            f.write(PANDOC_FILTER)

        subprocess.run(
            ['pandoc', '--lua-filter=filter.lua', '-t', 'gfm', '-o', 'temp.md', 'temp.tex'],
            cwd=tmp_dir,
            check=True,
        )

        with open(os.path.join(tmp_dir, 'temp.md'), 'r', encoding='utf-8') as f:
            md = f.read()

    return md


def pandoc_get_version():
    parts = subprocess.check_output(['pandoc', '--version']).decode().splitlines()[0].split(' ')[1].split('.')
    return tuple(map(int, parts))


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

    problem_meta['cases_data'] = []
    problem_meta['batches'] = {}
    problem_meta['normal_cases'] = []
    problem_meta['zipfile'] = os.path.join(problem_meta['tmp_dir'].name, 'tests.zip')

    # Tests can be aggregated into batches (called groups in Polygon).
    # Each batch can have one of two point policies:
    #    - complete-group: contestant gets points only if all tests in the batch are solved.
    #    - each-test: contestant gets points for each test solved
    # Our judge only supports complete-group batches.
    # For each-test batches, their tests are added as normal tests.
    # Each batch can also have a list of dependencies, which are other batches
    # that must be fully solved before the batch is run.
    # To support dependencies, we just add all dependent tests before the actual tests.
    # (There is actually a more elegant way to do this by using field `dependencies` in init.yml,
    # but site does not support it yet)
    # Our judge does cache result for each test, so the same test will not be run twice.
    # In addition, we only support dependencies for complete-group batches.
    # (Technically, we could support dependencies for each-test batch by splitting it
    # into multiple complete-group batches, but that's too complicated)

    groups = testset.find('groups')
    if groups is not None:
        for group in groups.getchildren():
            name = group.get('name')
            points = int(float(group.get('points', 0)))
            points_policy = group.get('points-policy')
            dependencies = group.find('dependencies')
            if dependencies is None:
                dependencies = []
            else:
                dependencies = [d.get('group') for d in dependencies.getchildren()]

            assert points_policy in ['complete-group', 'each-test']
            if points_policy == 'each-test' and len(dependencies) > 0:
                raise CommandError('dependencies are only supported for batches with complete-group point policy')

            problem_meta['batches'][name] = {
                'name': name,
                'points': points,
                'points_policy': points_policy,
                'dependencies': dependencies,
                'cases': [],
            }

    with zipfile.ZipFile(problem_meta['zipfile'], 'w') as tests_zip:
        input_path_pattern = testset.find('input-path-pattern').text
        answer_path_pattern = testset.find('answer-path-pattern').text
        for i, test in enumerate(testset.find('tests').getchildren()):
            points = int(float(test.get('points', 0)))
            input_path = input_path_pattern % (i + 1)
            answer_path = answer_path_pattern % (i + 1)
            input_file = f'{(i + 1):02d}.inp'
            output_file = f'{(i + 1):02d}.out'

            tests_zip.writestr(input_file, package.read(input_path))
            tests_zip.writestr(output_file, package.read(answer_path))

            problem_meta['cases_data'].append({
                'index': i,
                'input_file': input_file,
                'output_file': output_file,
                'points': points,
            })

            group = test.get('group', '')
            if group in problem_meta['batches']:
                problem_meta['batches'][group]['cases'].append(i)
            else:
                problem_meta['normal_cases'].append(i)

    def get_tests_by_batch(name):
        batch = problem_meta['batches'][name]

        if len(batch['dependencies']) == 0:
            return batch['cases']

        # Polygon guarantees no cycles
        cases = set(batch['cases'])
        for dependency in batch['dependencies']:
            cases.update(get_tests_by_batch(dependency))

        batch['dependencies'] = []
        batch['cases'] = list(cases)
        return batch['cases']

    each_test_batches = []
    for batch in problem_meta['batches'].values():
        if batch['points_policy'] == 'each-test':
            each_test_batches.append(batch['name'])
            problem_meta['normal_cases'] += batch['cases']
            continue

        batch['cases'] = get_tests_by_batch(batch['name'])

    for batch in each_test_batches:
        del problem_meta['batches'][batch]

    # Ignore zero-point batches
    zero_point_batches = [name for name, batch in problem_meta['batches'].items() if batch['points'] == 0]
    if len(zero_point_batches) > 0:
        print('Found zero-point batches:', ', '.join(zero_point_batches))
        print('Would you like ignore them (y/n)? ', end='', flush=True)
        if input().lower() in ['y', 'yes']:
            problem_meta['batches'] = {
                name: batch for name, batch in problem_meta['batches'].items() if batch['points'] > 0
            }
            print(f'Ignored {len(zero_point_batches)} zero-point batches')

    # Sort tests by index
    problem_meta['normal_cases'].sort()
    for batch in problem_meta['batches'].values():
        batch['cases'].sort()

    print(f'Found {len(testset.find("tests").getchildren())} tests!')
    print(f'Parsed as {len(problem_meta["batches"])} batches and {len(problem_meta["normal_cases"])} normal tests!')

    total_points = (sum(b['points'] for b in problem_meta['batches'].values()) +
                    sum(problem_meta['cases_data'][i]['points'] for i in problem_meta['normal_cases']))
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


def parse_statements(problem_meta, root, package):
    # Set default values
    problem_meta['name'] = ''
    problem_meta['description'] = ''
    problem_meta['translations'] = []
    problem_meta['tutorial'] = ''

    def process_images(text):
        image_cache = problem_meta['image_cache']

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

        for image_path in set(re.findall(r'!\[image\]\((.+?)\)', text)):
            text = text.replace(
                f'![image]({image_path})',
                f'![image]({save_image(image_path)})',
            )

        for img_tag in set(re.findall(r'<\s*img[^>]*>', text)):
            image_path = re.search(r'<\s*img[^>]+src\s*=\s*(["\'])(.*?)\1[^>]*>', img_tag).group(2)
            text = text.replace(
                img_tag,
                img_tag.replace(image_path, save_image(image_path)),
            )

        return text

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
            return

        raise CommandError('statement not found')

    translations = []
    tutorials = []
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
            'description': process_images(description),
        })

        tutorial = problem_properties['tutorial']
        if isinstance(tutorial, str) and tutorial != '':
            print(f'Converting tutorial in language {language} to Markdown')
            tutorial = pandoc_tex_to_markdown(tutorial)
            tutorials.append({
                'language': language,
                'tutorial': tutorial,
            })

    if len(translations) > 1:
        languages = [t['language'] for t in translations]
        print('Multilingual statements found:', languages)
        main_language = input_choice('Please select one as the main statement: ', languages)
    else:
        main_language = translations[0]['language']

    if len(tutorials) > 1:
        languages = [t['language'] for t in tutorials]
        print('Multilingual tutorials found:', languages)
        main_language = input_choice('Please select one as the sole tutorial: ', languages)
        problem_meta['tutorial'] = next(t for t in tutorials if t['language'] == main_language)['tutorial']
    elif len(tutorials) > 0:
        problem_meta['tutorial'] = tutorials[0]['tutorial']

    # Process images for only the selected tutorial
    problem_meta['tutorial'] = process_images(problem_meta['tutorial'])

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
    problem.authors.set(problem_meta['authors'])
    problem.curators.set(problem_meta['curators'])
    problem.types.set([ProblemType.objects.order_by('id').first()])  # Uncategorized
    problem.save()

    for tran in problem_meta['translations']:
        ProblemTranslation(
            problem=problem,
            language=tran['language'],
            name=tran['name'],
            description=tran['description'],
        ).save()

    if problem_meta['tutorial'] != '':
        Solution(
            problem=problem,
            is_public=False,
            publish_on=timezone.now(),
            content=problem_meta['tutorial'],
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

        for case_index in batch['cases']:
            order += 1
            case_data = problem_meta['cases_data'][case_index]
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

    for case_index in problem_meta['normal_cases']:
        order += 1
        case_data = problem_meta['cases_data'][case_index]
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
        parser.add_argument('--authors', help='username of problem author', nargs='*')
        parser.add_argument('--curators', help='username of problem curator', nargs='*')

    def handle(self, *args, **options):
        # Force using English
        translation.activate('en')

        # Check if pandoc is available
        if not shutil.which('pandoc'):
            raise CommandError('pandoc not installed')
        if pandoc_get_version() < (3, 0, 0):
            raise CommandError('pandoc version must be at least 3.0.0')

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

        problem_authors_args = options['authors'] or []
        problem_authors = []
        for username in problem_authors_args:
            try:
                profile = Profile.objects.get(user__username=username)
            except Profile.DoesNotExist:
                raise CommandError(f'user {username} does not exist')

            problem_authors.append(profile)

        problem_curators_args = options['curators'] or []
        problem_curators = []
        for username in problem_curators_args:
            try:
                profile = Profile.objects.get(user__username=username)
            except Profile.DoesNotExist:
                raise CommandError(f'user {username} does not exist')

            problem_curators.append(profile)

        # A dictionary to hold all problem information.
        problem_meta = {}
        problem_meta['image_cache'] = {}
        problem_meta['code'] = problem_code
        problem_meta['tmp_dir'] = tempfile.TemporaryDirectory()
        problem_meta['authors'] = problem_authors
        problem_meta['curators'] = problem_curators

        try:
            parse_checker(problem_meta, root, package)
            parse_tests(problem_meta, root, package)
            parse_statements(problem_meta, root, package)
            create_problem(problem_meta)
        except Exception:
            # Remove imported images
            for image_url in problem_meta['image_cache'].values():
                path = default_storage.path(os.path.join(settings.MARTOR_UPLOAD_MEDIA_DIR, os.path.basename(image_url)))
                os.remove(path)

            raise
        finally:
            problem_meta['tmp_dir'].cleanup()

        problem_url = 'https://' + Site.objects.first().domain + reverse('problem_detail', args=[problem_code])
        print(f'Imported successfully. View problem at {problem_url}')
