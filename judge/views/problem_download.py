import os
import zipfile
from io import BytesIO

import requests
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.views.generic import View
from django.views.generic.detail import SingleObjectMixin

from judge.models import Problem, problem_data_storage
from judge.utils.url import get_absolute_pdf_url
from judge.views.problem import ProblemMixin


class ProblemDownloadMixin(ProblemMixin):
    """Mixin to check if user can download problem data"""
    def get_object(self, queryset=None):
        problem = super().get_object(queryset)
        user = self.request.user

        # Check if user has permission to download problem data
        # Only editors (authors, curators) can download
        if not problem.is_editable_by(user):
            raise Http404()
        return problem


class DownloadProblemFullPackage(LoginRequiredMixin, ProblemDownloadMixin, SingleObjectMixin, View):
    """Download complete problem package: statement.pdf + tests.zip, all zipped together."""

    def get(self, request, *args, **kwargs):
        problem = self.get_object()

        try:
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:

                self._add_statement(zip_file, problem)
                self._add_pdf(zip_file, problem)

                data_files = getattr(problem, 'data_files', None)
                self._add_file_to_zip(zip_file, data_files, 'zipfile')
                self._add_file_to_zip(zip_file, data_files, 'custom_checker')
                self._add_file_to_zip(zip_file, data_files, 'custom_grader')
                self._add_file_to_zip(zip_file, data_files, 'custom_header')

            response = HttpResponse(buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{problem.code}_package.zip"'
            return response

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def _add_file_to_zip(self, zip_file, data_files, field_name):
        try:
            if data_files and getattr(data_files, field_name):
                file_path = getattr(data_files, field_name).name
                file_basename = os.path.basename(file_path)

                if problem_data_storage.exists(file_path):
                    with problem_data_storage.open(file_path, 'rb') as f:
                        zip_file.writestr(file_basename, f.read())
                else:
                    zip_file.writestr(f'{field_name}_error.txt', f'File recorded but not found on disk: {file_path}')
        except Exception as e:
            zip_file.writestr(f'{field_name}_error.txt', f'Error processing {field_name}: {str(e)}')

    def _add_pdf(self, zip_file, problem):
        """Fetch PDF from external URL and write to the zip file using its original filename."""
        if not problem.pdf_url:
            return

        try:
            parsed_url = get_absolute_pdf_url(problem.pdf_url)

            response = requests.get(parsed_url, timeout=10)
            response.raise_for_status()

            zip_file.writestr('statement.pdf', response.content)
        except requests.exceptions.RequestException as e:
            zip_file.writestr('statement_pdf_error.txt', f'Failed to download PDF ({problem.pdf_url}): {str(e)}')
        except Exception as e:
            zip_file.writestr('statement_pdf_error.txt', f'Error processing PDF ({problem.pdf_url}): {str(e)}')

    def _add_statement(self, zip_file, problem: Problem):
        """Add statement.pdf to the zip file if it exists."""
        try:
            statement = problem.description.strip()
            if statement:
                zip_file.writestr('statement.md', statement)
        except Exception as e:
            zip_file.writestr('statement_md_error.txt', f'Error processing statement: {str(e)}')
