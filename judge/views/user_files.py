import os

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from judge.forms import UserFileEditForm, UserFileUploadForm
from judge.models import UserFile
from judge.utils.user_file_access import UserFileAccessChain
from judge.utils.views import TitleMixin, generic_message

__all__ = [
    'UserFileListView', 'UserFileUploadView', 'UserFileDetailView',
    'UserFileEditView', 'UserFileDeleteView', 'UserFileDownloadView', 'UserFileAccessView'
]

_PERMISSION_DENIED_TITLE = _('Permission denied')
_PERMISSION_DENIED_MESSAGE = _('You do not have permission to use user files.')


class UserFileBaseMixin(TitleMixin):
    """Base mixin for user file views with common configuration."""

    model = UserFile
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    context_object_name = 'file'

    def get_queryset(self):
        """Base queryset - to be overridden by subclasses."""
        return UserFile.objects.all()


class UserFilePermissionMixin(UserFileBaseMixin):
    """Enforce login and model-level permission checks for user file actions."""

    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        if self.required_permission and not request.user.has_perm(self.required_permission):
            return generic_message(
                request,
                _PERMISSION_DENIED_TITLE,
                _PERMISSION_DENIED_MESSAGE,
                status=403,
            )

        return super().dispatch(request, *args, **kwargs)


class UserOwnedFilesMixin(UserFilePermissionMixin):
    """Mixin restricting mutating actions to owner-visible querysets."""

    def get_queryset(self):
        """Filter to only current user's files, except for superusers."""
        if self.request.user.is_superuser:
            return UserFile.objects.all()
        return UserFile.objects.filter(user=self.request.profile)


class PublicAccessMixin(UserFileBaseMixin):
    """Mixin providing permission-checked object access for public/private files."""

    access_chain = UserFileAccessChain()

    def get_object(self, queryset=None):
        """Load file by UUID and validate access through handler chain."""
        uuid_value = self.kwargs.get(self.slug_url_kwarg)
        try:
            file_obj = UserFile.objects.get(uuid=uuid_value)
        except UserFile.DoesNotExist:
            raise Http404('File not found or access denied.')

        return self.access_chain.authorize(self.request, file_obj)


class UserFileListView(UserOwnedFilesMixin, ListView):
    """List files uploaded by the current user."""

    title = 'My Files'
    template_name = 'user/files/file_list.html'
    paginate_by = 20
    context_object_name = 'files'

    def get_queryset(self):
        """Return files owned by the current user ordered by upload time."""
        return super().get_queryset().order_by('-uploaded_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'can_upload': True,
            'can_edit': True,
            'can_delete': True,
        })
        return context


class UserFileUploadView(UserOwnedFilesMixin, CreateView):
    """Upload a new file."""

    title = 'Upload New File'
    form_class = UserFileUploadForm
    template_name = 'user/files/file_upload.html'

    def form_valid(self, form):
        form.instance.user = self.request.profile
        form.instance.storage_scope = UserFile.STORAGE_SCOPE_MARTOR
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
    """View details of a single file with usage information and access control."""

    title = 'File Details'
    template_name = 'user/files/file_detail.html'

    def get_object(self, queryset=None):
        """Get object with additional permission checks for related problems/contests."""
        obj = super().get_object(queryset=queryset)
        self._check_related_access(obj)
        return obj

    def _check_related_access(self, file_obj):
        """Verify user can access the scoped context that references this file."""
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
    """Edit file metadata (description and visibility)."""

    title = 'Edit File'
    form_class = UserFileEditForm
    template_name = 'user/files/file_edit.html'

    def get_success_url(self):
        """Redirect back to file detail page after editing."""
        return reverse_lazy('user_file_detail', kwargs={'uuid': self.object.uuid})


class UserFileDeleteView(UserOwnedFilesMixin, DeleteView):
    """Delete a file with confirmation."""

    title = 'Delete File'
    template_name = 'user/files/file_delete.html'
    success_url = reverse_lazy('user_file_list')


class UserFileDownloadView(PublicAccessMixin, DetailView):
    """Serve a file while enforcing permission checks."""

    template_name = None  # No template needed for download

    def get_object(self, queryset=None):
        """Get object with strict permission verification."""
        return super().get_object(queryset=queryset)

    def _serve_file(self, request, as_attachment):
        """Serve file either as attachment (download) or inline (view)."""
        try:
            self.object = self.get_object()
        except Http404:
            raise

        self.object.update_last_accessed()

        try:
            download_name = self.object.get_resolved_filename()
            mime_type = self.object.get_resolved_mime_type()

            response = FileResponse(
                self.object.file.open('rb'),
                content_type=mime_type,
            )
            disposition_type = 'attachment' if as_attachment else 'inline'
            response['Content-Disposition'] = f'{disposition_type}; filename="{download_name}"'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        except (OSError, IOError) as e:
            return generic_message(
                request,
                'File Error',
                f'File not found or cannot be accessed: {str(e)}',
                status=404
            )

    def get(self, request, *args, **kwargs):
        """Handle file download with permission verification and access tracking."""
        return self._serve_file(request, as_attachment=True)


class UserFileAccessView(UserFileDownloadView):
    """View a file inline while preserving strict permission checks."""

    def get(self, request, *args, **kwargs):
        """Serve file inline for public sharing and browser viewing."""
        return self._serve_file(request, as_attachment=False)
