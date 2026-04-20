from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from judge.forms import UserFileUploadForm, UserFileEditForm
from judge.models import FileUsage, Problem, UserFile
from judge.utils.user_file_access import UserFileAccessChain
from judge.utils.views import TitleMixin, generic_message

__all__ = [
    'UserFileListView', 'UserFileUploadView', 'UserFileDetailView',
    'UserFileEditView', 'UserFileDeleteView', 'UserFileDownloadView', 'UserFileAccessView'
]


class UserFileBaseMixin(TitleMixin):
    """Base mixin for user file views with common configuration."""
    
    model = UserFile
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    context_object_name = 'file'
    
    def get_queryset(self):
        """Base queryset - to be overridden by subclasses."""
        return UserFile.objects.all()


class UserOwnedFilesMixin(UserFileBaseMixin):
    """Mixin restricting access to authenticated user's own files."""
    
    def dispatch(self, request, *args, **kwargs):
        """Require authentication for owned files."""
        if not request.user.is_authenticated:
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        """Filter to only current user's files."""
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
    """List all files uploaded by the current user and files used in their problems/contests."""
    
    title = 'My Files'
    template_name = 'user/files/file_list.html'
    paginate_by = 20
    context_object_name = 'files'
    
    def get_queryset(self):
        """Return files owned by user plus files referenced by user's problems."""
        user_profile = self.request.profile

        queryset = UserFile.objects.filter(user=user_profile).distinct()

        user_problem_ids = list(Problem.objects.filter(
            Q(authors=user_profile) | Q(curators=user_profile)
        ).values_list('id', flat=True))

        if user_problem_ids:
            problem_files = UserFile.objects.filter(
                usages__problem_id__in=user_problem_ids
            ).distinct()
            queryset = queryset | problem_files

        queryset = queryset.order_by('-uploaded_at')

        search = self.request.GET.get('search', '')
        file_type = self.request.GET.get('file_type', '')
        visibility = self.request.GET.get('visibility', '')

        if search:
            queryset = queryset.filter(
                Q(filename__icontains=search) | Q(description__icontains=search)
            )
        if file_type:
            queryset = queryset.filter(file_type=file_type)
        if visibility == 'public':
            queryset = queryset.filter(is_public=True)
        elif visibility == 'private':
            queryset = queryset.filter(is_public=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        """Add filter options and search parameters to context."""
        context = super().get_context_data(**kwargs)
        context.update({
            'search': self.request.GET.get('search', ''),
            'file_type': self.request.GET.get('file_type', ''),
            'visibility': self.request.GET.get('visibility', ''),
            'file_type_choices': UserFile.FILE_TYPE_CHOICES,
        })
        return context


class UserFileUploadView(UserOwnedFilesMixin, CreateView):
    """Upload a new file."""
    
    title = 'Upload New File'
    form_class = UserFileUploadForm
    template_name = 'user/files/file_upload.html'
    
    def form_valid(self, form):
        """Attach current user to the form instance before saving."""
        form.instance.user = self.request.profile
        return super().form_valid(form)
    
    def get_success_url(self):
        """Redirect to the file list after successful upload."""
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
        """Verify user can access problems that reference this file."""
        usages = FileUsage.objects.filter(user_file=file_obj, problem_id__isnull=False)

        for usage in usages:
            if usage.problem_id:
                try:
                    problem = Problem.objects.get(id=usage.problem_id)
                    if not self._can_access_problem(problem):
                        raise Http404('File access denied - related problem is not accessible.')
                except Problem.DoesNotExist:
                    raise Http404('File access denied - related problem not found.')
    
    def _can_access_problem(self, problem):
        """Check if current user can access a problem."""
        if problem is None:
            return True
        
        # If problem is public, anyone can see it
        if problem.is_public:
            return True
        
        # If user not authenticated, deny private problem access
        if not self.request.user.is_authenticated:
            return False
        
        # Check if user is problem owner or curator
        user_profile = self.request.profile
        if problem.authors.filter(id=user_profile.id).exists():
            return True
        if problem.curators.filter(id=user_profile.id).exists():
            return True
        
        # Default: deny private problem access for non-owners
        return False


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
