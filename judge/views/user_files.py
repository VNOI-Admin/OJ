from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.http import FileResponse, HttpResponseForbidden

from judge.forms import UserFileUploadForm, UserFileEditForm
from judge.models import UserFile

__all__ = ['UserFileListView', 'UserFileUploadView', 'UserFileDetailView', 'UserFileEditView', 'UserFileDeleteView', 'UserFileDownloadView']


class UserFileListView(LoginRequiredMixin, ListView):
    """List all files uploaded by the current user."""
    model = UserFile
    template_name = 'user/files/file_list.html'
    paginate_by = 20
    context_object_name = 'files'
    
    def get_queryset(self):
        """Return only files owned by the current user."""
        return UserFile.objects.filter(user=self.request.profile).order_by('-uploaded_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter and search functionality
        search = self.request.GET.get('search', '')
        file_type = self.request.GET.get('file_type', '')
        visibility = self.request.GET.get('visibility', '')
        
        queryset = self.get_queryset()
        
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
        
        context['search'] = search
        context['file_type'] = file_type
        context['visibility'] = visibility
        context['file_type_choices'] = UserFile.FILE_TYPE_CHOICES
        context['queryset'] = queryset
        context['object_list'] = self.paginate_queryset(queryset, self.paginate_by)
        context['page_obj'] = context['paginator'] = None
        
        if hasattr(self, 'paginator'):
            context['paginator'] = self.paginator
            context['page_obj'] = self.page_obj
            context['is_paginated'] = self.page_obj.has_next()
        
        return context
    
    def paginate_queryset(self, queryset, page_size):
        """Paginate the queryset."""
        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        self.paginator = paginator
        self.page_obj = page_obj
        return page_obj.object_list


class UserFileUploadView(LoginRequiredMixin, CreateView):
    """Upload a new file."""
    model = UserFile
    form_class = UserFileUploadForm
    template_name = 'user/files/file_upload.html'
    
    def form_valid(self, form):
        """Save the file with the current user as owner."""
        form.instance.user = self.request.profile
        response = super().form_valid(form)
        return response
    
    def get_success_url(self):
        """Redirect to the file detail page after upload."""
        return reverse_lazy('user_file_list')


class UserFileDetailView(LoginRequiredMixin, DetailView):
    """View details of a file."""
    model = UserFile
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    template_name = 'user/files/file_detail.html'
    context_object_name = 'file'
    
    def get_queryset(self):
        """Only allow viewing own files or public files."""
        return UserFile.objects.filter(
            Q(user=self.request.profile) | Q(is_public=True)
        )


class UserFileEditView(LoginRequiredMixin, UpdateView):
    """Edit file metadata."""
    model = UserFile
    form_class = UserFileEditForm
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    template_name = 'user/files/file_edit.html'
    context_object_name = 'file'
    
    def get_queryset(self):
        """Only allow editing own files."""
        return UserFile.objects.filter(user=self.request.profile)
    
    def get_success_url(self):
        """Redirect to the file detail page after editing."""
        return reverse_lazy('user_file_detail', kwargs={'uuid': self.object.uuid})


class UserFileDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a file."""
    model = UserFile
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    template_name = 'user/files/file_delete.html'
    success_url = reverse_lazy('user_file_list')
    context_object_name = 'file'
    
    def get_queryset(self):
        """Only allow deletion of own files."""
        return UserFile.objects.filter(user=self.request.profile)


class UserFileDownloadView(LoginRequiredMixin, DetailView):
    """Download a file."""
    model = UserFile
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    
    def get_queryset(self):
        """Allow downloading own files or public files."""
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
            from django.http import HttpResponse
            return HttpResponse(f'File not found or cannot be accessed: {str(e)}', status=404)
