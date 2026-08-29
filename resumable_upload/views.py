import datetime
import json
import logging
import os
import shutil
import uuid

import jwt
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from judge.models import Problem

logger = logging.getLogger(__name__)


def _get_jwt_secret():
    return getattr(settings, 'TUSD_JWT_SECRET', None) or settings.SECRET_KEY


def create_upload_intent_token(user_id, problem_code, file_type, file_name):
    expiry_seconds = getattr(settings, 'TUSD_JWT_EXPIRY_SECONDS', 7200)
    payload = {
        'sub': str(user_id),
        'problem_code': problem_code,
        'file_type': file_type,
        'file_name': file_name,
        'jti': str(uuid.uuid4()),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=expiry_seconds),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm='HS256')


def decode_upload_intent_token(token):
    return jwt.decode(token, _get_jwt_secret(), algorithms=['HS256'])


def move_uploaded_file(source_path, problem_code, file_name):
    if not os.path.exists(source_path):
        raise FileNotFoundError(f'tusd source file not found: {source_path}')

    dest_dir = os.path.join(settings.DMOJ_PROBLEM_DATA_ROOT, problem_code)
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, file_name)
    shutil.move(source_path, dest_path)

    info_path = source_path + '.info'
    if os.path.exists(info_path):
        try:
            os.remove(info_path)
        except OSError:
            pass

    return dest_path


class UploadIntentView(LoginRequiredMixin, View):
    http_method_names = ['post']
    raise_exception = True

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        problem_code = body.get('problem_code', '').strip()
        file_type = body.get('file_type', '').strip()
        file_name = body.get('file_name', '').strip()

        if not problem_code or not file_type or not file_name:
            return JsonResponse({'error': 'problem_code, file_type, and file_name are required.'}, status=400)

        allowed_file_types = getattr(settings, 'TUSD_ALLOWED_FILE_TYPES', ())
        if file_type not in allowed_file_types:
            return JsonResponse(
                {'error': f'file_type must be one of: {", ".join(allowed_file_types)}.'},
                status=400,
            )

        problem = get_object_or_404(Problem, code=problem_code)
        if not problem.is_editable_by(request.user):
            raise Http404

        token = create_upload_intent_token(request.user.pk, problem_code, file_type, file_name)
        return JsonResponse({
            'token': token,
            'tusd_endpoint': settings.TUSD_ENDPOINT,
        })


@method_decorator(csrf_exempt, name='dispatch')
class TusdHookView(View):
    http_method_names = ['post']

    def _verify_secret(self, request):
        hook_secret = getattr(settings, 'TUSD_HOOK_SECRET', None)
        if not hook_secret:
            return True
        return request.headers.get('X-Tusd-Hook-Secret') == hook_secret

    def post(self, request, *args, **kwargs):
        if not self._verify_secret(request):
            return JsonResponse({'error': 'Forbidden.'}, status=403)

        try:
            body = json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        hook_type = body.get('Type', '')
        token = body.get('Event', {}).get('Upload', {}).get('MetaData', {}).get('token', '')

        try:
            payload = decode_upload_intent_token(token)
        except jwt.InvalidTokenError:
            return JsonResponse({'RejectUpload': True}, status=200)

        if hook_type == 'pre-create':
            return JsonResponse({}, status=200)

        elif hook_type == 'pre-finish':
            upload_event = body.get('Event', {}).get('Upload', {})
            source_path = upload_event.get('Storage', {}).get('Path', '')
            if not source_path:
                return JsonResponse({'RejectUpload': True}, status=200)

            if getattr(settings, 'TUSD_DATA_DIR', None):
                source_path = os.path.join(settings.TUSD_DATA_DIR, os.path.basename(source_path))

            try:
                move_uploaded_file(source_path, payload['problem_code'], payload['file_name'])
            except Exception:
                logger.exception('pre-finish: failed to move file')
                return JsonResponse({'RejectUpload': True}, status=200)

            return JsonResponse({}, status=200)

        return JsonResponse({'error': f'Unsupported hook type: {hook_type!r}.'}, status=400)
