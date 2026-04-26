import json
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.views.generic.detail import BaseDetailView

from judge.models import UserFile
from judge.views.api.api_v2 import APIMixin, APILoginRequiredMixin, APIListView

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
        'file_type': user_file.file_type,
        'file_type_display': user_file.get_file_type_display(),
        'storage_scope': user_file.storage_scope,
        'size': user_file.size,
        'description': user_file.description,
        'is_public': user_file.is_public,
        'uploaded_at': user_file.uploaded_at.isoformat(),
        'last_accessed': user_file.last_accessed.isoformat(),
        'access_count': user_file.access_count,
        'usage_contexts': usages,
        'download_url': user_file.get_download_url(),
        'access_url': user_file.get_access_url(),
    }


class UserFilePermissionMixin(APILoginRequiredMixin):
    required_permission = None

    def setup_api(self, request, *args, **kwargs):
        super().setup_api(request, *args, **kwargs)
        if self.required_permission and not request.user.has_perm(self.required_permission):
            raise PermissionDenied()


class UserFileListView(UserFilePermissionMixin, APIListView):
    """API endpoint for listing user files with filtering support."""

    queryset = UserFile.objects.all()
    paginate_by = settings.DMOJ_API_PAGE_SIZE
    required_permission = 'judge.view_userfile'

    def get_unfiltered_queryset(self):
        if self.request.user.is_superuser:
            return UserFile.objects.all().order_by('-uploaded_at')
        return UserFile.objects.filter(user=self.request.profile).order_by('-uploaded_at')

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(filename__icontains=search) | Q(description__icontains=search)
            )

        file_type = self.request.GET.get('file_type', '').strip()
        if file_type and file_type in dict(UserFile.FILE_TYPE_CHOICES):
            queryset = queryset.filter(file_type=file_type)

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


class UserFileDetailView(UserFilePermissionMixin, APIMixin, BaseDetailView):
    """API endpoint for retrieving one user file."""

    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    required_permission = 'judge.view_userfile'

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


class UserFileDownloadView(UserFilePermissionMixin, APIMixin, BaseDetailView):
    """API endpoint for downloading a user file."""

    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    required_permission = 'judge.view_userfile'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return UserFile.objects.all()
        return UserFile.objects.filter(Q(user=self.request.profile) | Q(is_public=True))

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        if not self.object.can_view_by(request.user):
            raise PermissionDenied()

        self.object.update_last_accessed()

        try:
            download_name = self.object.get_resolved_filename()
            mime_type = self.object.get_resolved_mime_type()

            response = FileResponse(
                self.object.file.open('rb'),
                content_type=mime_type,
            )
            response['Content-Disposition'] = f'attachment; filename="{download_name}"'
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


class UserFileUploadView(UserFilePermissionMixin, APIMixin, BaseDetailView):
    """API endpoint for uploading a new user file."""

    queryset = UserFile.objects.all()
    required_permission = 'judge.add_userfile'

    def post(self, request):
        try:
            if request.content_type and 'multipart/form-data' in request.content_type:
                if 'file' not in request.FILES:
                    return self._error_response('file', 'No file provided', 400)

                uploaded_file = request.FILES['file']
                file_type = request.POST.get('file_type', 'other')
                storage_scope = request.POST.get('storage_scope', UserFile.STORAGE_SCOPE_MARTOR)
                description = request.POST.get('description', '')
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
                file_type = data.get('file_type', 'other')
                storage_scope = data.get('storage_scope', UserFile.STORAGE_SCOPE_MARTOR)
                description = data.get('description', '')
                is_public = data.get('is_public', False)

                uploaded_file = InMemoryUploadedFile(
                    file=BytesIO(file_data),
                    field_name='file',
                    name=filename,
                    content_type=data.get('content_type', 'application/octet-stream'),
                    size=len(file_data),
                    charset=None,
                )

            if file_type not in dict(UserFile.FILE_TYPE_CHOICES):
                return self._error_response('file_type', 'Invalid file type', 400)

            valid_scopes = {
                UserFile.STORAGE_SCOPE_PROBLEM,
                UserFile.STORAGE_SCOPE_CONTEST,
                UserFile.STORAGE_SCOPE_MARTOR,
            }
            if storage_scope not in valid_scopes:
                return self._error_response('storage_scope', 'Invalid storage scope', 400)

            user_file = UserFile(
                user=request.profile,
                file=uploaded_file,
                filename=uploaded_file.name,
                file_type=file_type,
                storage_scope=storage_scope,
                description=description,
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


class UserFileDeleteView(UserFilePermissionMixin, APIMixin, BaseDetailView):
    """API endpoint for deleting a user file."""

    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    required_permission = 'judge.delete_userfile'

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
