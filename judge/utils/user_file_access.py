from django.http import Http404


_ACCESS_DENIED_MESSAGE = 'File not found or access denied.'


class AccessContext:
    """Request/file pair passed through the authorization chain."""

    def __init__(self, request, file_obj):
        self.request = request
        self.file_obj = file_obj


class AccessHandler:
    """Base handler for chain-of-responsibility authorization checks."""

    def __init__(self, next_handler=None):
        self._next_handler = next_handler

    def set_next(self, handler):
        self._next_handler = handler
        return handler

    def handle(self, context):
        if self._next_handler is None:
            return context.file_obj
        return self._next_handler.handle(context)


class PublicFileAccessHandler(AccessHandler):
    """Allow immediate access for public files."""

    def handle(self, context):
        if context.file_obj.is_public:
            return context.file_obj
        return super().handle(context)


class AuthenticatedAccessHandler(AccessHandler):
    """Require authentication for non-public files."""

    def handle(self, context):
        if not context.request.user.is_authenticated:
            raise Http404(_ACCESS_DENIED_MESSAGE)
        return super().handle(context)


class OwnerAccessHandler(AccessHandler):
    """Require ownership for non-public files."""

    def handle(self, context):
        request_profile = getattr(context.request, 'profile', None)
        if request_profile is None or context.file_obj.user != request_profile:
            raise Http404(_ACCESS_DENIED_MESSAGE)
        return context.file_obj


class UserFileAccessChain:
    """Authorization chain for user file visibility."""

    def __init__(self):
        self._head = PublicFileAccessHandler()
        authenticated = self._head.set_next(AuthenticatedAccessHandler())
        authenticated.set_next(OwnerAccessHandler())

    def authorize(self, request, file_obj):
        context = AccessContext(request, file_obj)
        return self._head.handle(context)
