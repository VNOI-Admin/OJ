import hashlib
import logging
import os
import shutil
import time

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from judge.models import Problem
from judge.utils.problems import fast_delete_problem

__all__ = ('problem_garbage_collect', 'cleanup_expired_chunked_uploads')


@shared_task
def problem_garbage_collect():
    problems = Problem.expired_deletion.all()
    end = timezone.now() + settings.VNOJ_PROBLEM_GARBAGE_COLLECTOR_TIME_LIMIT
    for problem in problems:
        if timezone.now() > end:
            break
        fast_delete_problem(problem)


@shared_task
def cleanup_expired_chunked_uploads():

    upload_dir = os.path.join(settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR)
    if not os.path.exists(upload_dir):
        return

    now = time.time()
    expiry_seconds = settings.CHUNKED_UPLOAD_EXPIRY_HOURS * 3600

    for user_id_str in os.listdir(upload_dir):
        user_path = os.path.join(upload_dir, user_id_str)
        if not os.path.isdir(user_path):
            continue

        for upload_id in os.listdir(user_path):
            path = os.path.join(user_path, upload_id)
            if not os.path.isdir(path):
                continue

            try:
                mtime = os.path.getmtime(path)
                if now - mtime > expiry_seconds:
                    shutil.rmtree(path, ignore_errors=True)
                    meta_key = f'chunked_upload:{upload_id}:meta'
                    meta = cache.get(meta_key)
                    if meta:
                        file_id = meta.get('file_id')
                        if file_id:
                            raw_id = f'{user_id_str}:{file_id}'.encode()
                            file_key = f'chunked_upload_file:{hashlib.sha256(raw_id).hexdigest()}'
                            cache.delete(file_key)
                    cache.delete(meta_key)
                    cache.delete(f'chunked_upload:{upload_id}:chunks')
                    session_count_key = f'chunked_upload:active_sessions:{user_id_str}'
                    try:
                        current = cache.decr(session_count_key)
                        if current < 0:
                            cache.set(session_count_key, 0, timeout=expiry_seconds)
                    except ValueError:
                        cache.set(session_count_key, 0, timeout=expiry_seconds)
            except Exception:
                logging.getLogger(__name__).warning(f'Failed to cleanup expired chunked upload: {path}', exc_info=True)

        try:
            if not os.listdir(user_path):
                os.rmdir(user_path)
        except OSError:
            pass
