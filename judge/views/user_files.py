import os

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from judge.forms import UserFileEditForm, UserFileUploadForm
from judge.models import FileAttachment, UserFile
from judge.utils.user_file_access import authorize_file_access, serve_user_file
from judge.utils.views import TitleMixin

__all__ = [
    'UserFileListView', 'UserFileUploadView', 'UserFileDetailView',
    'UserFileEditView', 'UserFileDeleteView', 'UserFileBulkDeleteView',
    'UserFileAccessView',
    'UserFileSearchView', 'AttachmentAccessView',
]


class UserFileBaseMixin(TitleMixin):
    model = UserFile
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    context_object_name = 'file'

    def get_queryset(self):
        return UserFile.objects.none()


class UserFilePermissionMixin(UserFileBaseMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)


class UserOwnedFilesMixin(UserFilePermissionMixin):
    def get_queryset(self):
        if self.request.user.is_superuser:
            return UserFile.objects.all()
        return UserFile.objects.filter(user=self.request.profile)


class PublicAccessMixin(UserFileBaseMixin):
    def get_object(self, queryset=None):
        uuid_value = self.kwargs.get(self.slug_url_kwarg)
        try:
            file_obj = UserFile.objects.get(uuid=uuid_value)
        except UserFile.DoesNotExist:
            raise Http404('File not found or access denied.')

        return authorize_file_access(self.request, file_obj)


class UserFileListView(UserOwnedFilesMixin, ListView):
    title = 'My Files'
    template_name = 'user/files/file_list.html'
    paginate_by = 20
    context_object_name = 'files'

    def get_queryset(self):
        return super().get_queryset().order_by('-uploaded_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'can_upload': UserFile.can_upload_by(self.request.user),
            'can_edit': True,
            'can_delete': True,
        })
        return context


class UserFileUploadView(UserOwnedFilesMixin, CreateView):
    title = 'Upload New File'
    form_class = UserFileUploadForm
    template_name = 'user/files/file_upload.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not UserFile.can_upload_by(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.user = self.request.profile
        uploaded_file = form.cleaned_data.get('file')
        if uploaded_file:
            form.instance.filename = os.path.basename(uploaded_file.name)
        response = super().form_valid(form)
        messages.success(
            self.request,
            _('File "%(name)s" uploaded. UUID: %(uuid)s') % {
                'name': self.object.filename,
                'uuid': self.object.uuid,
            },
        )
        return response

    def get_success_url(self):
        return reverse_lazy('user_file_list')


class UserFileDetailView(PublicAccessMixin, DetailView):
    title = 'File Details'
    template_name = 'user/files/file_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = self.object.can_change_by(self.request.user)
        context.update({
            'can_edit': can_edit,
            'can_delete': self.object.can_delete_by(self.request.user),
        })
        if can_edit:
            context['form'] = UserFileEditForm(instance=self.object)
        return context


class UserFileEditView(UserOwnedFilesMixin, UpdateView):
    form_class = UserFileEditForm
    template_name = 'user/files/file_detail.html'

    def get_success_url(self):
        return reverse_lazy('user_file_detail', kwargs={'uuid': self.object.uuid})


class UserFileDeleteView(UserOwnedFilesMixin, DeleteView):
    title = 'Delete File'
    template_name = 'user/files/file_delete.html'
    success_url = reverse_lazy('user_file_list')


class UserFileBulkDeleteView(UserFilePermissionMixin, View):
    def post(self, request, *args, **kwargs):
        uuids = request.POST.getlist('uuids')
        if not uuids:
            messages.error(request, _('No files selected.'))
            return redirect('user_file_list')

        qs = UserFile.objects.filter(uuid__in=uuids)
        if not request.user.is_superuser:
            qs = qs.filter(user=request.profile)

        count, __ = qs.delete()
        messages.success(
            request,
            _('%(count)d file(s) deleted.') % {'count': count},
        )
        return redirect('user_file_list')


class UserFileAccessView(PublicAccessMixin, DetailView):
    template_name = None

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return serve_user_file(request, self.object)


class UserFileSearchView(LoginRequiredMixin, View):
    """JSON endpoint for Select2: search the current user's uploaded files."""

    def get(self, request):
        q = request.GET.get('q', '')
        qs = UserFile.objects.filter(
            user=request.profile,
            file_scope=UserFile.FileScope.ATTACHMENT,
        ).order_by('-uploaded_at')
        if q:
            qs = qs.filter(filename__icontains=q)
        results = [
            {'id': f.id, 'text': f.filename, 'size': f.size}
            for f in qs[:50]
        ]
        return JsonResponse({'results': results})


class AttachmentAccessView(View):
    """Serve a FileAttachment if the requesting user can view its parent object."""

    def get(self, request, pk):
        attachment = get_object_or_404(
            FileAttachment.objects.select_related('file', 'content_type'),
            pk=pk,
        )
        if not attachment.can_view_by(request.user):
            raise Http404

        return serve_user_file(request, attachment.file)
