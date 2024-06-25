from django.contrib.auth.backends import ModelBackend

from judge.models import Profile


class IPBasedAuthBackend(ModelBackend):
    def authenticate(self, request, ip_auth):
        user = None
        try:
            user = Profile.objects.select_related('user').get(ip_auth=ip_auth).user
        except Profile.DoesNotExist:
            pass
        return user if self.user_can_authenticate(user) else None
