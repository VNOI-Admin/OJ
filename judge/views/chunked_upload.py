import hashlib
import json
import math
import os
import re
import shutil
import uuid

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django_redis import get_redis_connection

LUA_INCR_IF_UNDER = """
local current = redis.call('GET', KEYS[1])
if current == false then
    redis.call('SETEX', KEYS[1], ARGV[2], 1)
    return 1
end
current = tonumber(current)
if current < tonumber(ARGV[1]) then
    redis.call('INCR', KEYS[1])
    return current + 1
end
return -1
"""

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def _validate_upload_id(upload_id):
    """Returns True if upload_id is a valid UUID v4 string."""
    return bool(upload_id and _UUID_RE.match(upload_id))


def _add_uploaded_chunk(upload_id, chunk_index):
    """Add chunk_index to the set of uploaded chunks using Redis SADD."""
    timeout = settings.CHUNKED_UPLOAD_EXPIRY_HOURS * 3600
    redis_conn = get_redis_connection('default')
    cache_key = cache.make_key(f'chunked_upload:{upload_id}:chunks')
    redis_conn.sadd(cache_key, chunk_index)
    redis_conn.expire(cache_key, timeout)


def _get_uploaded_chunks(upload_id):
    """Get sorted list of uploaded chunks from Redis."""
    redis_conn = get_redis_connection('default')
    cache_key = cache.make_key(f'chunked_upload:{upload_id}:chunks')
    members = redis_conn.smembers(cache_key)
    return sorted([int(m) for m in members])


def _get_uploaded_chunks_count(upload_id):
    """Get the count of uploaded chunks from Redis."""
    redis_conn = get_redis_connection('default')
    cache_key = cache.make_key(f'chunked_upload:{upload_id}:chunks')
    return redis_conn.scard(cache_key)


def _delete_uploaded_chunks(upload_id):
    """Delete the set of uploaded chunks from Redis."""
    redis_conn = get_redis_connection('default')
    cache_key = cache.make_key(f'chunked_upload:{upload_id}:chunks')
    redis_conn.delete(cache_key)


@login_required
@require_POST
def chunked_upload_init(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)

    file_size = data.get('file_size')
    chunk_size = data.get('chunk_size')
    total_chunks = data.get('total_chunks')
    filename = data.get('filename')
    file_id = data.get('file_id')

    if file_size is None or chunk_size is None or total_chunks is None or not filename or not file_id:
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    try:
        file_size = int(file_size)
        chunk_size = int(chunk_size)
        total_chunks = int(total_chunks)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid type for numerical fields'}, status=400)

    if file_size <= 0 or chunk_size <= 0 or total_chunks <= 0:
        return JsonResponse({'error': 'Numerical fields must be positive'}, status=400)

    if file_size > settings.CHUNKED_UPLOAD_MAX_FILE_SIZE:
        return JsonResponse({
            'error': f'File size exceeds maximum limit of {settings.CHUNKED_UPLOAD_MAX_FILE_SIZE} bytes.',
        }, status=400)

    if chunk_size != settings.CHUNKED_UPLOAD_CHUNK_SIZE:
        return JsonResponse({
            'error': f'Chunk size must be exactly {settings.CHUNKED_UPLOAD_CHUNK_SIZE} bytes',
        }, status=400)

    expected_total_chunks = math.ceil(file_size / chunk_size)
    if total_chunks != expected_total_chunks:
        return JsonResponse({'error': 'total_chunks mismatch'}, status=400)

    raw_id = f'{request.user.id}:{file_id}'.encode()
    file_key = f'chunked_upload_file:{hashlib.sha256(raw_id).hexdigest()}'
    existing_upload_id = cache.get(file_key)
    if existing_upload_id and _validate_upload_id(existing_upload_id):
        meta_key = f'chunked_upload:{existing_upload_id}:meta'
        meta = cache.get(meta_key)
        if meta and meta.get('user_id') == request.user.id:
            filename_safe = meta['safe_filename']
            target_path = os.path.join(
                settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR,
                str(request.user.id), existing_upload_id, filename_safe,
            )
            if os.path.exists(target_path):
                uploaded_chunks = _get_uploaded_chunks(existing_upload_id)
                return JsonResponse({
                    'upload_id': existing_upload_id,
                    'uploaded_chunks': uploaded_chunks,
                    'chunk_size': chunk_size,
                })

    session_count_key = f'chunked_upload:active_sessions:{request.user.id}'
    timeout = settings.CHUNKED_UPLOAD_EXPIRY_HOURS * 3600

    redis_conn = get_redis_connection('default')
    key = cache.make_key(session_count_key)
    max_parallel = getattr(settings, 'CHUNKED_UPLOAD_MAX_PARALLEL', 3)

    result = redis_conn.eval(LUA_INCR_IF_UNDER, 1, key, max_parallel, timeout)
    if result == -1:
        return JsonResponse({
            'error': (
                f'You have reached the maximum number of concurrent uploads ({max_parallel}). '
                'Please complete or cancel them.'
            ),
        }, status=429)

    # Initialize a new session
    upload_id = str(uuid.uuid4())
    ext = os.path.splitext(os.path.basename(filename))[1][:10]
    ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)
    safe_filename = f'{uuid.uuid4().hex}{ext}'

    upload_dir_path = os.path.join(
        settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR, str(request.user.id), upload_id,
    )

    user_media_dir = os.path.join(settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR, str(request.user.id))
    current_disk_usage = 0
    if os.path.exists(user_media_dir):
        for dirpath, _, filenames in os.walk(user_media_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    current_disk_usage += os.path.getsize(fp)

    max_disk = getattr(settings, 'CHUNKED_UPLOAD_MAX_USER_DISK', 20 * 1024 * 1024 * 1024)
    if current_disk_usage + file_size > max_disk:
        # Revert the quota increment since we are rejecting
        try:
            cache.decr(session_count_key)
        except ValueError:
            pass
        return JsonResponse({
            'error': 'User disk quota for temporary chunked uploads exceeded.',
        }, status=400)

    os.makedirs(upload_dir_path, exist_ok=True)
    target_path = os.path.join(upload_dir_path, safe_filename)

    # Pre-allocate sparse file
    with open(target_path, 'wb') as f:
        f.truncate(file_size)

    meta = {
        'filename': filename,
        'safe_filename': safe_filename,
        'file_size': file_size,
        'chunk_size': chunk_size,
        'total_chunks': total_chunks,
        'user_id': request.user.id,
        'file_id': file_id,
    }

    cache.set(f'chunked_upload:{upload_id}:meta', meta, timeout)
    cache.set(file_key, upload_id, timeout)

    return JsonResponse({
        'upload_id': upload_id,
        'uploaded_chunks': [],
        'chunk_size': chunk_size,
    })


@login_required
@require_POST
def chunked_upload_chunk(request):
    upload_id = request.POST.get('upload_id')
    chunk_index_str = request.POST.get('chunk_index')
    chunk_file = request.FILES.get('file')

    if not (upload_id and chunk_index_str is not None and chunk_file):
        return JsonResponse({'error': 'Missing required parameters'}, status=400)

    if not _validate_upload_id(upload_id):
        return JsonResponse({'error': 'Invalid upload ID format'}, status=400)

    try:
        chunk_index = int(chunk_index_str)
    except ValueError:
        return JsonResponse({'error': 'Invalid chunk index'}, status=400)

    meta_key = f'chunked_upload:{upload_id}:meta'
    meta = cache.get(meta_key)
    if not meta:
        return JsonResponse({'error': 'Upload session not found or expired'}, status=400)

    if meta.get('user_id') != request.user.id:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    total_chunks = meta['total_chunks']
    chunk_size = meta['chunk_size']
    file_size = meta['file_size']
    safe_filename = meta['safe_filename']

    if not (0 <= chunk_index < total_chunks):
        return JsonResponse({'error': 'Chunk index out of range'}, status=400)

    # Size validations
    expected_chunk_size = file_size - (chunk_index * chunk_size) if chunk_index == total_chunks - 1 else chunk_size
    if chunk_file.size != expected_chunk_size:
        return JsonResponse({
            'error': f'Chunk size mismatch. Expected {expected_chunk_size} bytes, got {chunk_file.size} bytes.',
        }, status=400)

    target_path = os.path.join(
        settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR, str(meta['user_id']), upload_id, safe_filename,
    )
    if not os.path.exists(target_path):
        return JsonResponse({'error': 'Target file not found'}, status=400)

    offset = chunk_index * chunk_size

    # Concurrent-safe file write via seek
    with open(target_path, 'r+b') as f:
        f.seek(offset)
        for chunk_data in chunk_file.chunks():
            f.write(chunk_data)
        _add_uploaded_chunk(upload_id, chunk_index)

    return JsonResponse({
        'status': 'ok',
        'uploaded_chunks': _get_uploaded_chunks_count(upload_id),
    })


@login_required
@require_POST
def chunked_upload_complete(request):
    upload_id = request.POST.get('upload_id')
    if not upload_id:
        return JsonResponse({'error': 'Missing upload_id'}, status=400)

    if not _validate_upload_id(upload_id):
        return JsonResponse({'error': 'Invalid upload ID format'}, status=400)

    meta_key = f'chunked_upload:{upload_id}:meta'
    meta = cache.get(meta_key)
    if not meta:
        return JsonResponse({'error': 'Upload session not found or expired'}, status=400)

    if meta.get('user_id') != request.user.id:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    total_chunks = meta['total_chunks']
    uploaded_count = _get_uploaded_chunks_count(upload_id)

    if uploaded_count < total_chunks:
        uploaded_list = _get_uploaded_chunks(upload_id)
        uploaded_set = set(uploaded_list)
        missing = [i for i in range(total_chunks) if i not in uploaded_set]
        return JsonResponse({
            'status': 'incomplete',
            'missing_chunks': missing,
        }, status=400)

    safe_filename = meta['safe_filename']
    target_path = os.path.join(
        settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR, str(meta['user_id']), upload_id, safe_filename,
    )
    if not os.path.exists(target_path):
        return JsonResponse({'error': 'Target file not found'}, status=400)

    # Clean up resumable file mapping
    file_id = meta.get('file_id')
    if file_id:
        raw_id = f'{request.user.id}:{file_id}'.encode()
        file_key = f'chunked_upload_file:{hashlib.sha256(raw_id).hexdigest()}'
        cache.delete(file_key)

    # Mark completed in cache for consuming view verification
    meta['status'] = 'completed'
    timeout = settings.CHUNKED_UPLOAD_EXPIRY_HOURS * 3600
    cache.set(meta_key, meta, timeout)

    return JsonResponse({
        'status': 'completed',
        'upload_id': upload_id,
        'safe_filename': safe_filename,
    })


def get_completed_upload(upload_id, user_id):
    """
    Retrieves the local file path and original filename of a completed upload session.
    Returns (file_path, original_filename) if valid and completed, otherwise None.
    """
    if not _validate_upload_id(upload_id):
        return None

    meta_key = f'chunked_upload:{upload_id}:meta'
    meta = cache.get(meta_key)
    if not meta or meta.get('user_id') != user_id or meta.get('status') != 'completed':
        return None

    safe_filename = meta['safe_filename']
    original_filename = meta['filename']
    file_path = os.path.join(
        settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR, str(user_id), upload_id, safe_filename,
    )
    if os.path.exists(file_path):
        return file_path, original_filename
    return None


def clean_completed_upload(upload_id, meta=None):
    """
    Removes the temporary chunked upload folder and cached keys.
    """
    if not _validate_upload_id(upload_id):
        return

    if meta:
        user_id = meta.get('user_id')
        if user_id:
            session_count_key = f'chunked_upload:active_sessions:{user_id}'
            try:
                current = cache.decr(session_count_key)
                if current < 0:
                    cache.set(session_count_key, 0, timeout=settings.CHUNKED_UPLOAD_EXPIRY_HOURS * 3600)
            except ValueError:
                cache.set(session_count_key, 0, timeout=settings.CHUNKED_UPLOAD_EXPIRY_HOURS * 3600)
            upload_dir = os.path.join(settings.MEDIA_ROOT, settings.CHUNKED_UPLOAD_MEDIA_DIR, str(user_id), upload_id)
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir, ignore_errors=True)
                try:
                    user_dir = os.path.dirname(upload_dir)
                    if not os.listdir(user_dir):
                        os.rmdir(user_dir)
                except OSError:
                    pass

    cache.delete(f'chunked_upload:{upload_id}:meta')
    _delete_uploaded_chunks(upload_id)


def get_completed_uploaded_file(request, upload_id_param, content_type='application/octet-stream'):
    """
    Checks if upload_id_param exists in request.POST. If so, retrieves the completed
    upload file and wraps it as a Django UploadedFile.
    Returns (upload_id, uploaded_file) or (None, None).
    Note: the caller is responsible for calling uploaded_file.close() in a finally block.
    """
    upload_id = request.POST.get(upload_id_param)
    if not upload_id:
        return None, None

    if not _validate_upload_id(upload_id):
        return upload_id, None

    upload_info = get_completed_upload(upload_id, request.user.id)
    if not upload_info:
        return upload_id, None

    from django.core.files.uploadedfile import UploadedFile
    file_path, original_filename = upload_info
    try:
        f_assembled = open(file_path, 'rb')
        try:
            uploaded_file = UploadedFile(
                file=f_assembled,
                name=original_filename,
                content_type=content_type,
                size=os.path.getsize(file_path),
            )
            return upload_id, uploaded_file
        except Exception:
            f_assembled.close()
            return upload_id, None
    except Exception:
        return upload_id, None


@login_required
@require_POST
def chunked_upload_cancel(request):
    upload_id = request.POST.get('upload_id')
    if not upload_id:
        return JsonResponse({'error': 'Missing upload_id'}, status=400)

    if not _validate_upload_id(upload_id):
        return JsonResponse({'error': 'Invalid upload ID format'}, status=400)

    meta_key = f'chunked_upload:{upload_id}:meta'
    meta = cache.get(meta_key)
    if not meta:
        return JsonResponse({'status': 'ok'})

    if meta.get('user_id') != request.user.id:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    file_id = meta.get('file_id')
    if file_id:
        raw_id = f'{request.user.id}:{file_id}'.encode()
        file_key = f'chunked_upload_file:{hashlib.sha256(raw_id).hexdigest()}'
        cache.delete(file_key)

    clean_completed_upload(upload_id, meta=meta)
    return JsonResponse({'status': 'ok'})
