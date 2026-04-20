from judge.views.user_files import (
    UserFileAccessView as BaseUserFileAccessView,
    UserFileDeleteView as BaseUserFileDeleteView,
    UserFileDetailView as BaseUserFileDetailView,
    UserFileDownloadView as BaseUserFileDownloadView,
    UserFileEditView as BaseUserFileEditView,
    UserFileListView as BaseUserFileListView,
    UserFileUploadView as BaseUserFileUploadView,
)

__all__ = [
    'UserFileListView',
    'UserFileUploadView',
    'UserFileDetailView',
    'UserFileEditView',
    'UserFileDeleteView',
    'UserFileDownloadView',
    'UserFileAccessView',
]


class UserFileListView(BaseUserFileListView):
    pass


class UserFileUploadView(BaseUserFileUploadView):
    pass


class UserFileDetailView(BaseUserFileDetailView):
    pass


class UserFileEditView(BaseUserFileEditView):
    pass


class UserFileDeleteView(BaseUserFileDeleteView):
    pass


class UserFileDownloadView(BaseUserFileDownloadView):
    pass


class UserFileAccessView(BaseUserFileAccessView):
    pass
