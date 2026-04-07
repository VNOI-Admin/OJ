from celery import shared_task
from django.conf import settings
from django.utils import timezone

from judge.models import Problem
from judge.utils.problems import fast_delete_problem


@shared_task
def problem_garbage_collect():
    problems = Problem.expired_deletion.all()
    end = timezone.now() + settings.VNOJ_PROBLEM_GARBAGE_COLLECTOR_TIME_LIMIT
    for problem in problems:
        if timezone.now() > end:
            break
        fast_delete_problem(problem)
