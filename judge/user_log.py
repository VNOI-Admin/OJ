import logging
from datetime import timedelta

from django.utils.timezone import now

from judge.models import Profile

logger = logging.getLogger('judge.user_log')

LAST_ACCESS_UPDATE_INTERVAL = timedelta(minutes=10)


class LogUserAccessMiddleware(object):
    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (hasattr(request, 'user') and request.user.is_authenticated and
                not getattr(request, 'no_profile_update', False)):
            # Decided on using REMOTE_ADDR as nginx will translate it to the external IP that hits it.
            ip = request.META.get('REMOTE_ADDR')
            profile = getattr(request, 'profile', None)
            if (profile is not None and profile.last_access is not None and
                    now() - profile.last_access < LAST_ACCESS_UPDATE_INTERVAL and (not ip or ip == profile.ip)):
                return response

            updates = {'last_access': now()}
            if ip:
                updates['ip'] = ip
                if profile is not None and ip != profile.ip:
                    logger.info('%s,%s,%s', request.user.username, profile.ip, ip)
            Profile.objects.filter(user_id=request.user.pk).update(**updates)

        return response
