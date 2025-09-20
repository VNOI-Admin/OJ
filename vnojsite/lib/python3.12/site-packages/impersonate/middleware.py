# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import SimpleLazyObject

from .compat import reverse
from .helpers import User, check_allow_for_uri, check_allow_for_user, check_read_only
from .settings import settings


class ImpersonateMiddleware(MiddlewareMixin):
    def process_request(self, request):
        _usr = request.user  # save as local var to prevent infinite recursion

        def _get_usr():
            # This is all to avoid querying for the "User" instance before
            # it's actually necessary.
            _usr.is_impersonate = False
            return _usr

        request.user = SimpleLazyObject(_get_usr)
        request.impersonator = None

        if '_impersonate' in request.session and request.user.is_authenticated:
            if settings.MAX_DURATION:
                if request.path == reverse('impersonate-stop'):
                    return

                if '_impersonate_start' not in request.session:
                    return

                start_time = datetime.fromtimestamp(
                    request.session['_impersonate_start'], timezone.utc
                )
                delta = timedelta(seconds=settings.MAX_DURATION)

                if datetime.now(timezone.utc) - start_time > delta:
                    return redirect('impersonate-stop')

            new_user_id = request.session['_impersonate']
            if isinstance(new_user_id, User):
                # Edge case for issue 15
                new_user_id = new_user_id.pk

            try:
                new_user = User.objects.get(pk=new_user_id)
            except User.DoesNotExist:
                return

            if check_read_only(request) and request.method not in ['GET', 'HEAD', 'OPTIONS']:
                return HttpResponseNotAllowed(['GET', 'HEAD', 'OPTIONS'])

            if check_allow_for_user(request, new_user) and check_allow_for_uri(
                request.path
            ):
                request.impersonator = request.user
                request.user = new_user
                request.user.is_impersonate = True
                request.user.impersonator = request.impersonator

        request.real_user = request.impersonator or request.user
