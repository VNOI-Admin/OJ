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


class SuperuserAccessHandler(AccessHandler):
    """Allow superusers to bypass all checks."""

    def handle(self, context):
        if context.request.user.is_authenticated and context.request.user.is_superuser:
            return context.file_obj
        return super().handle(context)


class PublicFileAccessHandler(AccessHandler):
    """Allow immediate access for public files."""

    def handle(self, context):
        if context.file_obj.is_public and not context.file_obj.requires_context_authorization:
            return context.file_obj
        return super().handle(context)


class ScopedAuthenticationAccessHandler(AccessHandler):
    """Require authentication for scoped files before context checks."""

    def handle(self, context):
        if not context.file_obj.requires_context_authorization:
            return super().handle(context)
        if not context.request.user.is_authenticated:
            raise Http404(_ACCESS_DENIED_MESSAGE)
        return super().handle(context)


class ScopedOwnerAccessHandler(AccessHandler):
    """Allow scoped file owner to access directly."""

    def handle(self, context):
        if not context.file_obj.requires_context_authorization:
            return super().handle(context)
        if context.file_obj.is_owned_by(context.request.user):
            return context.file_obj
        return super().handle(context)


class ScopedContestAccessHandler(AccessHandler):
    """Allow access when user can see any related contest context."""

    def handle(self, context):
        if not context.file_obj.requires_context_authorization:
            return super().handle(context)
        if context.file_obj.can_view_by_contest_context(context.request.user):
            return context.file_obj
        return super().handle(context)


class ScopedProblemAccessHandler(AccessHandler):
    """Allow access when user can see any related problem context."""

    def handle(self, context):
        if not context.file_obj.requires_context_authorization:
            return super().handle(context)
        if context.file_obj.can_view_by_problem_context(context.request.user):
            return context.file_obj
        raise Http404(_ACCESS_DENIED_MESSAGE)


class PrivateFileAccessHandler(AccessHandler):
    """Require model-level permissions for non-public files."""

    def handle(self, context):
        if not context.file_obj.can_view_by(context.request.user):
            raise Http404(_ACCESS_DENIED_MESSAGE)
        return context.file_obj


class UserFileAccessChain:
    """Authorization chain for user file visibility."""

    def __init__(self):
        self._head = SuperuserAccessHandler()
        public = self._head.set_next(PublicFileAccessHandler())
        scoped_auth = public.set_next(ScopedAuthenticationAccessHandler())
        scoped_owner = scoped_auth.set_next(ScopedOwnerAccessHandler())
        scoped_contest = scoped_owner.set_next(ScopedContestAccessHandler())
        scoped_problem = scoped_contest.set_next(ScopedProblemAccessHandler())
        scoped_problem.set_next(PrivateFileAccessHandler())

    def authorize(self, request, file_obj):
        context = AccessContext(request, file_obj)
        return self._head.handle(context)
