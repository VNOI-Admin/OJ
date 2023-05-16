from django.contrib.auth.backends import ModelBackend

from judge.models import Profile


class IPBasedAuthBackend(ModelBackend):
    def authenticate(self, request, ip_address=None):
        try:
            user = Profile.objects.filter(ip=ip_address).select_related('user').first().user
        except Profile.DoesNotExist:
            user = None
        return user
