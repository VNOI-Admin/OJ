from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, View

from judge.models import FileAttachment, UserFile
from judge.utils.user_file_access import authorize_file_access, serve_user_file
from judge.utils.views import TitleMixin

__all__ = [
    'UserFileListView', 'UserFileDetailView', 'UserFileDeleteView',
    'UserFileAccessView', 'UserFileSearchView', 'AttachmentAccessView',
]


class UserFileMixin(TitleMixin, LoginRequiredMixin):
    model = UserFile
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    context_object_name = 'file'


class UserFileListView(UserFileMixin, ListView):
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
        return UserFile.objects.filter(user=self.target_user.profile).order_by('-uploaded_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['target_user'] = self.target_user
        return context


class UserFileDetailView(UserFileMixin, DetailView):
    template_name = 'user/files/file_detail.html'

    def get_object(self, queryset=None):
        file_obj = super().get_object(queryset)
        authorize_file_access(self.request, file_obj)
        return file_obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_delete'] = self.object.can_delete_by(self.request.user)
        context['used_in'] = self.object.attachments.select_related('content_type').all()
        return context

    def get_title(self):
        return self.object.filename


class UserFileDeleteView(LoginRequiredMixin, View):
    """POST-only: delete one or more files by UUID. Single delete reuses this endpoint."""

    def post(self, request):
        uuids = request.POST.getlist('uuids')[:50]
        list_url = reverse('user_file_list', args=[request.user.username])
        if not uuids:
            messages.error(request, _('No files selected.'))
            return redirect(list_url)

        qs = UserFile.objects.filter(uuid__in=uuids, user=request.profile)

        count = qs.delete()[0]
        messages.success(request, _('%(count)d file(s) deleted.') % {'count': count})
        return redirect(list_url)


class UserFileAccessView(LoginRequiredMixin, View):
    def get(self, request, uuid):
        try:
            file_obj = UserFile.objects.get(uuid=uuid)
        except UserFile.DoesNotExist:
            raise Http404
        authorize_file_access(request, file_obj)
        return serve_user_file(request, file_obj)


class UserFileSearchView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '')
        qs = UserFile.objects.filter(
            user=request.profile,
            file_scope=UserFile.FileScope.ATTACHMENT,
        ).order_by('-uploaded_at')
        if q:
            qs = qs.filter(filename__icontains=q)
        return JsonResponse({'results': [
            {'id': f.id, 'text': f.filename, 'size': f.size}
            for f in qs[:50]
        ]})


class AttachmentAccessView(View):
    def get(self, request, pk):
        attachment = get_object_or_404(
            FileAttachment.objects.select_related('file', 'content_type'),
            pk=pk,
        )
        if not attachment.can_view_by(request.user):
            raise Http404
        return serve_user_file(request, attachment.file)
