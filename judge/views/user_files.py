import os

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from judge.forms import UserFileEditForm, UserFileUploadForm
from judge.models import UserFile
from judge.utils.user_file_access import UserFileAccessChain
from judge.utils.views import TitleMixin, generic_message

__all__ = [
    'UserFileListView', 'UserFileUploadView', 'UserFileDetailView',
    'UserFileEditView', 'UserFileDeleteView', 'UserFileBulkDeleteView',
    'UserFileDownloadView', 'UserFileAccessView',
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
    access_chain = UserFileAccessChain()

    def get_object(self, queryset=None):
        uuid_value = self.kwargs.get(self.slug_url_kwarg)
        try:
            file_obj = UserFile.objects.get(uuid=uuid_value)
        except UserFile.DoesNotExist:
            raise Http404('File not found or access denied.')

        return self.access_chain.authorize(self.request, file_obj)


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
        # Uploading on /files needs an explicit grant; unprivileged users may
        # only see files attached through problems/contests/the editor.
        if request.user.is_authenticated and not UserFile.can_upload_by(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.user = self.request.profile
        # Files uploaded directly on the /files page are user-owned uploads,
        # not markdown-editor images, so tag them with the user scope.
        form.instance.storage_scope = UserFile.STORAGE_SCOPE_USER
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

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        self._check_related_access(obj)
        return obj

    def _check_related_access(self, file_obj):
        # Scoped files are only visible to people who can reach the problem or
        # contest that references them.
        if file_obj.requires_context_authorization and not file_obj.can_view_by_context(self.request.user):
            raise Http404('File access denied - related context is not accessible.')

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

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.usages.exists():
            messages.error(request, _('Cannot delete: file is currently in use.'))
            return redirect('user_file_detail', uuid=self.object.uuid)
        return super().post(request, *args, **kwargs)


class UserFileBulkDeleteView(UserFilePermissionMixin, View):
    def post(self, request, *args, **kwargs):
        uuids = request.POST.getlist('uuids')
        if not uuids:
            messages.error(request, _('No files selected.'))
            return redirect('user_file_list')

        qs = UserFile.objects.filter(uuid__in=uuids)
        if not request.user.is_superuser:
            qs = qs.filter(user=request.profile)

        deletable_pks = list(qs.filter(usages__isnull=True).values_list('pk', flat=True))
        count = len(deletable_pks)
        skipped = qs.count() - count
        UserFile.objects.filter(pk__in=deletable_pks).delete()

        messages.success(
            request,
            _('%(count)d file(s) deleted.') % {'count': count},
        )
        if skipped:
            messages.warning(
                request,
                _('%(count)d file(s) skipped: still in use.') % {'count': skipped},
            )
        return redirect('user_file_list')


class UserFileDownloadView(PublicAccessMixin, DetailView):
    template_name = None

    def _serve_file(self, request, as_attachment):
        self.object = self.get_object()
        self.object.update_last_accessed()

        try:
            mime_type, content_disposition = self.object.get_content_disposition(as_attachment)

            response = FileResponse(
                self.object.file.open('rb'),
                content_type=mime_type,
            )
            response['Content-Disposition'] = content_disposition
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        except (OSError, IOError) as e:
            return generic_message(
                request,
                'File Error',
                f'File not found or cannot be accessed: {str(e)}',
                status=404,
            )

    def get(self, request, *args, **kwargs):
        return self._serve_file(request, as_attachment=True)


class UserFileAccessView(UserFileDownloadView):
    def get(self, request, *args, **kwargs):
        return self._serve_file(request, as_attachment=False)
