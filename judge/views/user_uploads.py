import mimetypes
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, View

from judge.models import FileAttachment, UserUpload
from judge.utils.views import TitleMixin, add_file_response, generic_message

__all__ = [
    'UserUploadListView', 'UserUploadDetailView', 'UserUploadDeleteView',
    'UserUploadAccessView', 'AttachmentAccessView', 'UserUploadCreateView',
]


def serve_user_upload(request, user_upload, filename=None):
    """Build an inline HTTP response for a UserUpload, using X-Accel-Redirect when available."""
    filename = filename or user_upload.filename
    try:
        # TODO: what should we do if martor image is an attachment?
        response = HttpResponse()
        response['Content-Type'] = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        add_file_response(request, response, user_upload.get_internal_url_path(), user_upload.get_file_path())
        return response
    except (OSError, IOError):
        return generic_message(request, 'File Error', _('File not found.'), status=404)


class UserUploadMixin(TitleMixin, LoginRequiredMixin):
    model = UserUpload
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    context_object_name = 'file'


class UserUploadListView(UserUploadMixin, ListView):
    template_name = 'user/files/file_list.html'
    context_object_name = 'files'
    paginate_by = 50
    title = _('User files')

    def dispatch(self, request, *args, **kwargs):
        target = get_object_or_404(User, username=kwargs['user'])
        if request.user.is_authenticated and not request.user.is_superuser and request.user != target:
            raise PermissionDenied()
        self.target_user = target
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return UserUpload.objects.filter(user=self.target_user.profile).order_by('-uploaded_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['target_user'] = self.target_user
        return context


class UserUploadDetailView(UserUploadMixin, DetailView):
    template_name = 'user/files/file_detail.html'

    def get_object(self, queryset=None):
        file_obj = super().get_object(queryset)
        if not file_obj.is_accessible_by(self.request.user):
            raise Http404('File not found or access denied.')
        return file_obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_delete'] = self.object.can_delete_by(self.request.user)
        context['used_in'] = self.object.attachments.select_related('content_type').all()
        return context

    def get_title(self):
        return self.object.filename


class UserUploadDeleteView(LoginRequiredMixin, View):
    """POST-only: delete one or more files by UUID. Single delete reuses this endpoint."""

    def post(self, request):
        uuids = request.POST.getlist('uuids')[:50]
        list_url = reverse('user_upload_list', args=[request.user.username])
        if not uuids:
            messages.error(request, _('No files selected.'))
            return redirect(list_url)

        qs = UserUpload.objects.filter(uuid__in=uuids, user=request.profile)

        count = qs.delete()[0]
        messages.success(request, _('%(count)d file(s) deleted.') % {'count': count})
        return redirect(list_url)


class UserUploadAccessView(LoginRequiredMixin, View):
    def get(self, request, uuid):
        try:
            file_obj = UserUpload.objects.get(uuid=uuid)
        except UserUpload.DoesNotExist:
            raise Http404
        if not file_obj.is_accessible_by(request.user):
            raise Http404('File not found or access denied.')
        return serve_user_upload(request, file_obj)


class AttachmentAccessView(View):
    def get(self, request, pk):
        attachment = get_object_or_404(
            FileAttachment.objects.select_related('file', 'content_type'),
            pk=pk,
        )
        if not attachment.can_view_by(request.user):
            raise Http404
        return serve_user_upload(request, attachment.file, filename=attachment.get_display_name())


class UserUploadCreateView(LoginRequiredMixin, View):
    def post(self, request):
        f = request.FILES.get('file')
        if not f:
            return JsonResponse({'error': _('No file provided.')}, status=400)
        ext = os.path.splitext(f.name)[1].lstrip('.').lower()
        if ext not in settings.USER_UPLOAD_ATTACHMENT_SAFE_EXTS:
            return JsonResponse({'error': _('Invalid file type.')}, status=400)
        if f.size > settings.USER_UPLOAD_ATTACHMENT_MAX_SIZE:
            return JsonResponse({'error': _('File too large.')}, status=400)
        user_upload = UserUpload(file=f, file_scope=UserUpload.FileScope.ATTACHMENT, user=request.profile)
        custom_name = request.POST.get('filename', '').strip()
        if custom_name:
            if os.path.splitext(custom_name)[1].lower() != os.path.splitext(f.name)[1].lower():
                return JsonResponse({'error': _('Filename extension must match the uploaded file.')}, status=400)
            user_upload.filename = custom_name
        user_upload.save()
        return JsonResponse({'id': user_upload.id, 'filename': user_upload.filename})
