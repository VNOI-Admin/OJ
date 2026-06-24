import mimetypes

from django.http import Http404, HttpResponse

from judge.utils.views import add_file_response, generic_message


def authorize_file_access(request, file_obj):
    user = request.user
    if user.is_authenticated and (user.is_superuser or file_obj.is_owned_by(user)):
        return file_obj
    raise Http404('File not found or access denied.')


def serve_user_file(request, user_file):
    """Build an inline HTTP response for a UserFile, using X-Accel-Redirect when available."""
    try:
        response = HttpResponse()
        response['Content-Type'] = mimetypes.guess_type(user_file.filename)[0] or 'application/octet-stream'
        response['Content-Disposition'] = f'inline; filename="{user_file.filename}"'
        add_file_response(request, response, user_file.get_url_path(), user_file.get_file_path())
        return response
    except (OSError, IOError) as e:
        return generic_message(request, 'File Error', 'File not found: {}'.format(e), status=404)
