from django.contrib.auth.backends import ModelBackend

from judge.models import Profile


class IPBasedAuthBackend(ModelBackend):
    def authenticate(self, request, ip_address=None):
        try:
            profile = Profile.objects.filter(ip=ip_address).order_by('-last_access').select_related('user').first()
            if profile is None:
                return None
            return profile.user
        except Profile.DoesNotExist:
            user = None
        return user
