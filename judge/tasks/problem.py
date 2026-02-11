import shutil
from celery import shared_task
from django.conf import settings
from django.db import transaction

from judge.models import ContestMoss, ContestProblem, Problem, ProblemData, Submission, SubmissionSource, \
    SubmissionTestCase
from judge.models.contest import ContestSubmission
from judge.utils.celery import Progress


__all__ = ('delete_problem',)


@shared_task(bind=True)
def delete_problem(self, problem_id):
    """
    Asynchronously delete a problem and all related objects in batches.

    This task performs a hard delete of a problem by:
    0. Hiding and renaming the problem immediately (idempotent - safe to retry)
    1. Deleting submission-related objects in batches (SubmissionTestCase, SubmissionSource, ContestSubmission)
    2. Deleting submissions themselves in batches
    3. Deleting contest-related objects (ContestProblem, ContestMoss)
    4. Deleting problem data files
    5. Deleting the problem itself (which cascades remaining small tables)

    Args:
        problem_id: The ID of the problem to delete
    """
    try:
        problem = Problem.objects.get(id=problem_id)
    except Problem.DoesNotExist:
        return 0

    batch_size = getattr(settings, 'VNOJ_PROBLEM_DELETE_BATCH_SIZE', 5000)

    with Progress(self, 1, stage='Hiding problem') as p:
        with transaction.atomic():
            problem.is_public = False
            new_code = f'__deleting_{problem.id}_{problem.code}'[:32]
            problem.code = new_code
            problem.save(update_fields=['is_public', 'code'])
        p.did(1)

    with Progress(self, 4, stage='Deleting submission data') as p:
        while True:
            with transaction.atomic():
                testcase_ids = list(
                    SubmissionTestCase.objects.filter(submission__problem_id=problem_id)
                    .values_list('id', flat=True)[:batch_size],
                )
                if not testcase_ids:
                    break
                SubmissionTestCase.objects.filter(id__in=testcase_ids).delete()

        p.did(1)

        while True:
            with transaction.atomic():
                source_ids = list(
                    SubmissionSource.objects.filter(submission__problem_id=problem_id)
                    .values_list('id', flat=True)[:batch_size],
                )
                if not source_ids:
                    break
                SubmissionSource.objects.filter(id__in=source_ids).delete()

        p.did(1)

        while True:
            with transaction.atomic():
                contest_sub_ids = list(
                    ContestSubmission.objects.filter(submission__problem_id=problem_id)
                    .values_list('id', flat=True)[:batch_size],
                )
                if not contest_sub_ids:
                    break
                ContestSubmission.objects.filter(id__in=contest_sub_ids).delete()

        p.did(1)

        while True:
            with transaction.atomic():
                submission_ids = list(Submission.objects.filter(problem_id=problem_id)
                                      .values_list('id', flat=True)[:batch_size])
                if not submission_ids:
                    break
                Submission.objects.filter(id__in=submission_ids).delete()

        p.did(1)

    with Progress(self, 2, stage='Deleting contest data') as p:
        ContestProblem.objects.filter(problem_id=problem_id).delete()
        p.did(1)

        ContestMoss.objects.filter(problem_id=problem_id).delete()
        p.did(1)

    with Progress(self, 1, stage='Deleting problem files') as p:
        try:
            problem_data = ProblemData.objects.get(problem_id=problem_id)
            if problem_data.zipfile:
                try:
                    shutil.rmtree(problem_data.zipfile.path, ignore_errors=True)
                except Exception:
                    pass
            problem_data.delete()
        except ProblemData.DoesNotExist:
            pass
        p.did(1)

    with Progress(self, 1, stage='Deleting problem') as p:
        problem.delete()
        p.did(1)

    return problem_id
