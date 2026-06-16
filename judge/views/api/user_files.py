import json
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.views import View
from django.views.generic.detail import BaseDetailView

from judge.forms import UserFileUploadForm
from judge.models import UserFile
from judge.utils.user_file_access import UserFileAccessChain
from judge.views.api.api_v2 import APIListView, APILoginRequiredMixin, APIMixin

__all__ = [
    'UserFileListView',
    'UserFileUploadView',
    'UserFileDetailView',
    'UserFileDeleteView',
    'UserFileDownloadView',
]


def serialize_user_file(user_file):
    usages = [{
        'type': usage.usage_type,
        'label': usage.get_context_label(),
    } for usage in user_file.usages.all()]

    return {
        'id': str(user_file.uuid),
        'filename': user_file.filename,
        'storage_scope': user_file.storage_scope,
        'size': user_file.size,
        'is_public': user_file.is_public,
        'uploaded_at': user_file.uploaded_at.isoformat(),
        'last_accessed': user_file.last_accessed.isoformat(),
        'access_count': user_file.access_count,
        'usage_contexts': usages,
        'download_url': user_file.get_download_url(),
        'access_url': user_file.get_access_url(),
    }


class UserFileListView(APILoginRequiredMixin, APIListView):
    queryset = UserFile.objects.all()
    paginate_by = settings.DMOJ_API_PAGE_SIZE

    def get_unfiltered_queryset(self):
        if self.request.user.is_superuser:
            return UserFile.objects.all().order_by('-uploaded_at')
        return UserFile.objects.filter(user=self.request.profile).order_by('-uploaded_at')

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(filename__icontains=search)

        storage_scope = self.request.GET.get('storage_scope', '').strip()
        if storage_scope and storage_scope in {
            UserFile.STORAGE_SCOPE_PROBLEM,
            UserFile.STORAGE_SCOPE_CONTEST,
            UserFile.STORAGE_SCOPE_MARTOR,
        }:
            queryset = queryset.filter(storage_scope=storage_scope)

        visibility = self.request.GET.get('visibility', '').strip()
        if visibility == 'public':
            queryset = queryset.filter(is_public=True)
        elif visibility == 'private':
            queryset = queryset.filter(is_public=False)

        sort = self.request.GET.get('sort', '-uploaded_at').strip()
        valid_sorts = [
            'uploaded_at', '-uploaded_at', 'filename', '-filename',
            'size', '-size', 'access_count', '-access_count',
        ]
        if sort in valid_sorts:
            queryset = queryset.order_by(sort)

        return queryset

    def get_object_data(self, obj):
        return serialize_user_file(obj)


class UserFileDetailView(APILoginRequiredMixin, APIMixin, BaseDetailView):
    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return UserFile.objects.all()
        return UserFile.objects.filter(user=self.request.profile)

    def get_object_data(self, obj):
        return serialize_user_file(obj)

    def get_api_data(self, context):
        return {
            'object': self.get_object_data(self.object),
        }


class UserFileDownloadView(APILoginRequiredMixin, APIMixin, BaseDetailView):
    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return UserFile.objects.all()
        return UserFile.objects.filter(Q(user=self.request.profile) | Q(is_public=True))

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            UserFileAccessChain().authorize(request, self.object)
        except Http404:
            raise PermissionDenied()

        self.object.update_last_accessed()

        try:
            mime_type, content_disposition = self.object.get_content_disposition(as_attachment=True)

            response = FileResponse(
                self.object.file.open('rb'),
                content_type=mime_type,
            )
            response['Content-Disposition'] = content_disposition
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        except (OSError, IOError) as e:
            return JsonResponse({
                'error': 'File not found or cannot be accessed',
                'details': str(e),
            }, status=404)

    def get_object_data(self, obj):
        return {}

    def get_api_data(self, context):
        return {}


class UserFileUploadView(APILoginRequiredMixin, APIMixin, View):
    def post(self, request):
        if not UserFile.can_upload_by(request.user):
            raise PermissionDenied()
        try:
            if request.content_type and 'multipart/form-data' in request.content_type:
                if 'file' not in request.FILES:
                    return self._error_response('file', 'No file provided', 400)

                uploaded_file = request.FILES['file']
                storage_scope = request.POST.get('storage_scope', UserFile.STORAGE_SCOPE_MARTOR)
                is_public = request.POST.get('is_public', 'false').lower() == 'true'
            else:
                try:
                    data = json.loads(request.body)
                except json.JSONDecodeError:
                    return self._error_response('body', 'Invalid JSON', 400)

                if 'file' not in data or 'filename' not in data:
                    return self._error_response('file', 'File and filename required', 400)

                try:
                    file_data = bytes.fromhex(data['file'])
                except (ValueError, TypeError):
                    return self._error_response('file', 'Invalid file encoding', 400)

                filename = data['filename']
                storage_scope = data.get('storage_scope', UserFile.STORAGE_SCOPE_MARTOR)
                is_public = data.get('is_public', False)

                uploaded_file = InMemoryUploadedFile(
                    file=BytesIO(file_data),
                    field_name='file',
                    name=filename,
                    content_type=data.get('content_type', 'application/octet-stream'),
                    size=len(file_data),
                    charset=None,
                )

            valid_scopes = {
                UserFile.STORAGE_SCOPE_PROBLEM,
                UserFile.STORAGE_SCOPE_CONTEST,
                UserFile.STORAGE_SCOPE_MARTOR,
            }
            if storage_scope not in valid_scopes:
                return self._error_response('storage_scope', 'Invalid storage scope', 400)

            if uploaded_file.size > UserFileUploadForm.MAX_UPLOAD_SIZE:
                return self._error_response('file', 'File size exceeds maximum allowed size of 500 MB', 400)

            user_file = UserFile(
                user=request.profile,
                file=uploaded_file,
                filename=uploaded_file.name,
                storage_scope=storage_scope,
                is_public=is_public,
            )
            user_file.save()

            return JsonResponse({
                **serialize_user_file(user_file),
                'message': 'File uploaded successfully',
            }, status=201)
        except Exception as e:
            return self._error_response('unknown', str(e), 500)

    def _error_response(self, field, message, status=400):
        return JsonResponse({
            'error': {
                'field': field,
                'message': message,
            },
        }, status=status)

    def get_object_data(self, obj):
        return {}

    def get_api_data(self, context):
        return {}


class UserFileDeleteView(APILoginRequiredMixin, APIMixin, BaseDetailView):
    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return UserFile.objects.all()
        return UserFile.objects.filter(user=self.request.profile)

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()

        if not self.object.can_delete_by(request.user):
            raise PermissionDenied()

        usages = self.object.usages.count()
        if usages > 0:
            return JsonResponse({
                'error': f'Cannot delete file: it is in use in {usages} context(s)',
            }, status=400)

        self.object.delete()

        return JsonResponse({
            'message': 'File deleted successfully',
        }, status=200)

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)

    def get_object_data(self, obj):
        return {}

    def get_api_data(self, context):
        return {}
