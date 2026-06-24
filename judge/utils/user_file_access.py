from django.http import Http404


def authorize_file_access(request, file_obj):
    user = request.user
    if user.is_authenticated and (user.is_superuser or file_obj.is_owned_by(user)):
        return file_obj
    raise Http404('File not found or access denied.')
