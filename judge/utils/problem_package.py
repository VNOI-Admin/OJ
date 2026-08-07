import json
import os
import shutil
import tempfile
import zipfile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from judge.models import Language, Problem, ProblemGroup, ProblemType, problem_data_storage


MANIFEST_FIELDS = (
    'code',
    'name',
    'description',
    'time_limit',
    'memory_limit',
    'short_circuit',
    'submission_source_visibility_mode',
    'testcase_visibility_mode',
    'testcase_result_visibility_mode',
    'allow_view_feedback',
    'points',
    'partial',
)


class ProblemPackageError(ValueError):
    pass


def can_use_problem_packages(user):
    return settings.VNOJ_PROBLEM_PACKAGE_ENABLED and user.is_authenticated and user.is_superuser


def export_problem(problem, destination, export_code=None, prefix_name=''):
    """Export one problem; bulk export can call this once for each problem."""
    manifest = {field: getattr(problem, field) for field in MANIFEST_FIELDS}
    manifest['code'] = export_code or problem.code
    manifest['name'] = prefix_name + problem.name

    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as package:
        package.writestr('problem.json', json.dumps(manifest, ensure_ascii=False))
        if problem_data_storage.exists(problem.code):
            data_directory = problem_data_storage.path(problem.code)
            for root, directories, filenames in os.walk(data_directory):
                directories.sort()
                for filename in sorted(filenames):
                    path = os.path.join(root, filename)
                    archive_name = os.path.relpath(path, data_directory)
                    if archive_name != 'problem.json':
                        package.write(path, archive_name)
    return destination


def _read_package(package_path, destination):
    try:
        with zipfile.ZipFile(package_path) as package:
            package.extractall(destination)
    except (OSError, zipfile.BadZipFile) as error:
        raise ProblemPackageError('The package is not a valid ZIP file.') from error

    manifest_path = os.path.join(destination, 'problem.json')
    try:
        with open(manifest_path, encoding='utf-8') as manifest_file:
            manifest = json.load(manifest_file)
        if not isinstance(manifest, dict):
            raise TypeError
        return {field: manifest[field] for field in MANIFEST_FIELDS}
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ProblemPackageError('The package must contain a valid problem.json file.') from error


def import_problem(package_path, code, user, temporary_root=None):
    """Import one problem; bulk import can call this once for each package."""
    try:
        Problem._meta.get_field('code').run_validators(code)
    except ValidationError as error:
        raise ProblemPackageError('The new problem code is invalid.') from error
    if Problem.objects.filter(code=code).exists():
        raise ProblemPackageError('A problem with this code already exists.')

    group = ProblemGroup.objects.order_by('pk').first()
    problem_type = ProblemType.objects.order_by('pk').first()
    if group is None or problem_type is None:
        raise ProblemPackageError('A default problem group and type must exist before importing.')

    with tempfile.TemporaryDirectory(dir=temporary_root) as extracted_directory:
        data = _read_package(package_path, extracted_directory)
        data['code'] = code
        data.update({
            'group': group,
            'is_public': False,
            'is_manually_managed': True,
            'date': timezone.now(),
        })
        problem = Problem(**data)
        try:
            problem.full_clean(exclude=('deleted_at',))
        except ValidationError as error:
            raise ProblemPackageError('problem.json contains invalid problem configuration.') from error

        data_directory = problem_data_storage.path(code)
        os.makedirs(os.path.dirname(data_directory), exist_ok=True)
        try:
            os.mkdir(data_directory)
        except FileExistsError as error:
            raise ProblemPackageError('The problem data directory already exists.') from error
        try:
            shutil.copytree(extracted_directory, data_directory, dirs_exist_ok=True)
            with transaction.atomic():
                problem.save()
                problem.curators.add(user.profile)
                problem.types.add(problem_type)
                problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
        except IntegrityError as error:
            shutil.rmtree(data_directory, ignore_errors=True)
            raise ProblemPackageError('A problem with this code already exists.') from error
        except Exception:
            shutil.rmtree(data_directory, ignore_errors=True)
            raise
    return problem
