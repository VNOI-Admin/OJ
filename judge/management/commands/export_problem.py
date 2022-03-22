import json
import os
import shutil

from django.core.management.base import BaseCommand
from django.utils import timezone

from judge.models import Language, Problem, ProblemGroup, ProblemType
from judge.utils.problem_data import ProblemDataStorage

problem_data_storage = ProblemDataStorage()


def export_problem(code, export_name=None):
    export_name = export_name or code

    problem = Problem.objects.get(code=code)

    # Retrieve
    data = {
        'code': export_name,  # Use for custom names
        'name': problem.name,
        'description': problem.description,
        'time_limit': problem.time_limit,
        'memory_limit': problem.memory_limit,
        'short_circuit': problem.short_circuit,
        'batch_policy': problem.batch_policy,
        'points': problem.points,
        'partial': problem.partial,
    }

    tmp_dir = os.path.join('/', 'tmp', export_name)
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.mkdir(tmp_dir)

    json.dump(data, open(os.path.join(tmp_dir, 'problem.json'), 'w'))
    if problem_data_storage.exists(code):
        shutil.copytree(problem_data_storage.path(code), tmp_dir, dirs_exist_ok=True)
    package_dir = shutil.make_archive(os.path.join('/', 'tmp', export_name), 'zip', tmp_dir)
    shutil.rmtree(tmp_dir)  # Remove unused directory after packing

    return package_dir


def import_problem(path):
    tmp_dir = os.path.join('/', 'tmp', os.path.splitext(os.path.basename(path))[0])
    shutil.unpack_archive(path, tmp_dir, 'zip')
    data = json.load(open(os.path.join(tmp_dir, 'problem.json')))

    problem = Problem.objects.create(**data, is_manually_managed=True, group=ProblemGroup.objects.first())
    problem.types.add(ProblemType.objects.first())
    problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
    problem.date = timezone.now()
    problem.save()
    test_files_path = problem_data_storage.path(data['code'])
    shutil.copytree(tmp_dir, test_files_path, dirs_exist_ok=True)

    return problem


class Command(BaseCommand):
    help = 'create export/import problems'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        pass
