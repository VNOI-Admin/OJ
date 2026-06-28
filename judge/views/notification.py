from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView

from judge.models import Notification
from judge.utils.cache_helper import unread_notification_count_cache_factory
from judge.utils.diggpaginator import DiggPaginator
from judge.utils.views import TitleMixin, paginate_query_context

__all__ = ['NotificationList', 'NotificationAjax', 'NotificationMarkRead']

STATUS_CHOICES = ('all', 'unread', 'read')


class NotificationMixin(LoginRequiredMixin):
    @property
    def status(self):
        status = self.request.GET.get('status', 'all')
        return status if status in STATUS_CHOICES else 'all'

    def base_queryset(self):
        return Notification.objects.filter(recipient=self.request.profile)

    def filtered_queryset(self):
        queryset = self.base_queryset()
        if self.status == 'unread':
            queryset = queryset.filter(read=False).order_by('-priority', '-time')
        elif self.status == 'read':
            queryset = queryset.filter(read=True)
        return queryset


class NotificationList(NotificationMixin, TitleMixin, ListView):
    model = Notification
    template_name = 'notification/list.html'
    context_object_name = 'notifications'
    paginate_by = 50
    paginator_class = DiggPaginator

    def get_title(self):
        return _('Notifications')

    def get_queryset(self):
        return self.filtered_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status'] = self.status
        context.update(paginate_query_context(self.request))
        return context


class NotificationAjax(NotificationMixin, View):
    """Recent notifications for the navbar dropdown."""

    def get(self, request, *args, **kwargs):
        notifications = list(self.filtered_queryset()[:10])
        data = [{
            'id': n.id,
            'title': n.title,
            'body': n.body,
            'url': n.url,
            'read': n.read,
            'time': n.time.isoformat(),
        } for n in notifications]
        return JsonResponse({
            'notifications': data,
            'unread_count': request.profile.unread_notification_count,
        })


class NotificationMarkRead(LoginRequiredMixin, View):
    """Mark a single notification read/unread, or all of them read."""

    def post(self, request, *args, **kwargs):
        profile = request.profile
        queryset = Notification.objects.filter(recipient=profile)
        if request.POST.get('all') == '1':
            queryset.filter(read=False).update(read=True)
        else:
            try:
                notification_id = int(request.POST.get('id'))
            except (TypeError, ValueError):
                return JsonResponse({'error': 'invalid id'}, status=400)
            read = request.POST.get('read', '1') == '1'
            queryset.filter(id=notification_id).update(read=read)
        unread_notification_count_cache_factory(profile.id).delete_cache()
        return JsonResponse({'unread_count': profile.unread_notification_count})
