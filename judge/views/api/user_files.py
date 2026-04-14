import json
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic.detail import BaseDetailView
from django.views.generic.list import BaseListView

from judge.models import UserFile, FileUsage, Profile
from judge.views.api.api_v2 import APIMixin, APILoginRequiredMixin, APIListView

__all__ = ['UserFileListView', 'UserFileDetailView', 'UserFileDownloadView', 'UserFileUploadView']


class UserFileListView(APILoginRequiredMixin, APIListView):
    """
    API endpoint for listing user's files with filtering and search.
    """
    queryset = UserFile.objects.all()
    paginate_by = settings.DMOJ_API_PAGE_SIZE
    
    def get_unfiltered_queryset(self):
        """Return only the current user's files."""
        return UserFile.objects.filter(user=self.request.profile)
    
    def filter_queryset(self, queryset):
        """Apply filtering to the queryset."""
        queryset = super().filter_queryset(queryset)
        
        # Search by filename
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(filename__icontains=search) | Q(description__icontains=search)
            )
        
        # Filter by file type
        file_type = self.request.GET.get('file_type', '').strip()
        if file_type and file_type in dict(UserFile.FILE_TYPE_CHOICES):
            queryset = queryset.filter(file_type=file_type)
        
        # Filter by visibility
        visibility = self.request.GET.get('visibility', '').strip()
        if visibility == 'public':
            queryset = queryset.filter(is_public=True)
        elif visibility == 'private':
            queryset = queryset.filter(is_public=False)
        
        # Sort
        sort = self.request.GET.get('sort', '-uploaded_at').strip()
        valid_sorts = ['uploaded_at', '-uploaded_at', 'filename', '-filename', 'size', '-size', 'access_count', '-access_count']
        if sort in valid_sorts:
            queryset = queryset.order_by(sort)
        
        return queryset
    
    def get_object_data(self, obj):
        """Serialize a UserFile object."""
        usages = []
        for usage in obj.usages.all():
            usages.append({
                'type': usage.usage_type,
                'label': usage.get_context_label(),
            })
        
        return {
            'id': str(obj.uuid),
            'filename': obj.filename,
            'file_type': obj.file_type,
            'file_type_display': obj.get_file_type_display(),
            'size': obj.size,
            'description': obj.description,
            'is_public': obj.is_public,
            'uploaded_at': obj.uploaded_at.isoformat(),
            'last_accessed': obj.last_accessed.isoformat(),
            'access_count': obj.access_count,
            'usage_contexts': usages,
            'download_url': obj.get_download_url(),
        }
    
    def get_api_data(self, context):
        """Format the API response."""
        page = context['page_obj']
        objects = context['object_list']
        return {
            'current_object_count': len(objects),
            'objects_per_page': page.paginator.per_page,
            'page_index': page.number,
            'has_more': page.has_next(),
            'objects': [self.get_object_data(obj) for obj in objects],
        }


class UserFileDetailView(APILoginRequiredMixin, APIMixin, BaseDetailView):
    """
    API endpoint for retrieving a single file's details.
    """
    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    
    def get_queryset(self):
        """Only allow access to own files."""
        return UserFile.objects.filter(user=self.request.profile)
    
    def get_object_data(self, obj):
        """Serialize a UserFile object."""
        usages = []
        for usage in obj.usages.all():
            usages.append({
                'type': usage.usage_type,
                'label': usage.get_context_label(),
            })
        
        return {
            'id': str(obj.uuid),
            'filename': obj.filename,
            'file_type': obj.file_type,
            'file_type_display': obj.get_file_type_display(),
            'size': obj.size,
            'description': obj.description,
            'is_public': obj.is_public,
            'uploaded_at': obj.uploaded_at.isoformat(),
            'last_accessed': obj.last_accessed.isoformat(),
            'access_count': obj.access_count,
            'usage_contexts': usages,
            'download_url': obj.get_download_url(),
        }
    
    def get_api_data(self, context):
        return {
            'object': self.get_object_data(self.object),
        }


class UserFileDownloadView(APILoginRequiredMixin, BaseDetailView):
    """
    API endpoint for downloading a file.
    Increments access count and updates last_accessed timestamp.
    """
    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    
    def get_queryset(self):
        """Allow access to own files or public files."""
        return UserFile.objects.filter(
            Q(user=self.request.profile) | Q(is_public=True)
        )
    
    def get(self, request, *args, **kwargs):
        """Handle file download."""
        self.object = self.get_object()
        
        # Update access tracking
        self.object.update_last_accessed()
        
        # Return file
        try:
            response = FileResponse(self.object.file.open('rb'))
            response['Content-Type'] = 'application/octet-stream'
            response['Content-Disposition'] = f'attachment; filename="{self.object.filename}"'
            return response
        except (OSError, IOError) as e:
            return JsonResponse({
                'error': 'File not found or cannot be accessed',
                'details': str(e),
            }, status=404)


class UserFileUploadView(APILoginRequiredMixin, APIMixin, BaseDetailView):
    """
    API endpoint for uploading new files.
    Expects multipart form data or JSON with base64 encoded file.
    """
    queryset = UserFile.objects.all()
    
    def post(self, request):
        """Handle file upload."""
        try:
            # Get form data
            if request.content_type and 'multipart/form-data' in request.content_type:
                # Multipart upload
                if 'file' not in request.FILES:
                    return self._error_response('file', 'No file provided', 400)
                
                uploaded_file = request.FILES['file']
                file_type = request.POST.get('file_type', 'other')
                description = request.POST.get('description', '')
                is_public = request.POST.get('is_public', 'false').lower() == 'true'
            
            else:
                # JSON upload (base64 encoded file)
                try:
                    data = json.loads(request.body)
                except json.JSONDecodeError:
                    return self._error_response('body', 'Invalid JSON', 400)
                
                if 'file' not in data or 'filename' not in data:
                    return self._error_response('file', 'File and filename required', 400)
                
                try:
                    file_data = bytes.fromhex(data['file'])  # Assume hex encoded
                except (ValueError, TypeError):
                    return self._error_response('file', 'Invalid file encoding', 400)
                
                filename = data['filename']
                file_type = data.get('file_type', 'other')
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
            
            # Validate file type
            if file_type not in dict(UserFile.FILE_TYPE_CHOICES):
                return self._error_response('file_type', 'Invalid file type', 400)
            
            # Create UserFile
            user_file = UserFile(
                user=request.profile,
                file=uploaded_file,
                filename=uploaded_file.name,
                file_type=file_type,
                description=description,
                is_public=is_public,
            )
            user_file.save()
            
            return JsonResponse(self.get_success_response(user_file), status=201)
        
        except Exception as e:
            return self._error_response('unknown', str(e), 500)
    
    def _error_response(self, field, message, status=400):
        """Return an error response."""
        return JsonResponse({
            'error': {
                'field': field,
                'message': message,
            },
        }, status=status)
    
    def get_success_response(self, obj):
        """Return successful upload response."""
        usages = []
        for usage in obj.usages.all():
            usages.append({
                'type': usage.usage_type,
                'label': usage.get_context_label(),
            })
        
        return {
            'id': str(obj.uuid),
            'filename': obj.filename,
            'file_type': obj.file_type,
            'file_type_display': obj.get_file_type_display(),
            'size': obj.size,
            'description': obj.description,
            'is_public': obj.is_public,
            'uploaded_at': obj.uploaded_at.isoformat(),
            'last_accessed': obj.last_accessed.isoformat(),
            'access_count': obj.access_count,
            'usage_contexts': usages,
            'download_url': obj.get_download_url(),
            'message': 'File uploaded successfully',
        }


class UserFileDeleteView(APILoginRequiredMixin, APIMixin, BaseDetailView):
    """
    API endpoint for deleting a file.
    """
    queryset = UserFile.objects.all()
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    
    def get_queryset(self):
        """Only allow deletion of own files."""
        return UserFile.objects.filter(user=self.request.profile)
    
    def delete(self, request, *args, **kwargs):
        """Handle file deletion."""
        self.object = self.get_object()
        
        # Check if file is in use
        usages = self.object.usages.count()
        if usages > 0:
            return JsonResponse({
                'error': f'Cannot delete file: it is in use in {usages} context(s)'
            }, status=400)
        
        # Delete the file
        self.object.delete()
        
        return JsonResponse({
            'message': 'File deleted successfully',
        }, status=200)
    
    def post(self, request, *args, **kwargs):
        """Handle DELETE via POST (for compatibility)."""
        return self.delete(request, *args, **kwargs)
    
    def get_api_data(self, context):
        return {}
