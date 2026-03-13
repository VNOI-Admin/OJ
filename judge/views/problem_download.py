import os
import zipfile
from io import BytesIO
from urllib.parse import urlparse

import requests
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views.generic import ListView, View

from judge.models import Problem, problem_data_storage
from judge.utils.views import DiggPaginatorMixin, TitleMixin
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

    def get_problem(self, problem_code):
        """Helper method to fetch and validate problem for View-based classes"""
        problem = get_object_or_404(Problem, code=problem_code)

        # Check if user can access the problem
        if not problem.is_accessible_by(self.request.user):
            raise Http404()

        # Check if user has permission to download problem data
        if not problem.is_editable_by(self.request.user):
            raise Http404()

        return problem


class ProblemDownloadListView(LoginRequiredMixin, DiggPaginatorMixin, TitleMixin, ListView):
    """List view showing all problems user can download"""
    model = Problem
    template_name = 'problem/download_list.html'
    context_object_name = 'problems'
    paginate_by = 50
    title = _('Problem Downloads')

    def get_queryset(self):
        """Get problems that user can edit (download)"""
        user = self.request.user

        if not user.is_authenticated:
            return Problem.objects.none()

        # Get editable problems
        queryset = Problem.get_editable_problems(user)

        # Annotate with test data info
        queryset = queryset.select_related('data_files').prefetch_related(
            'authors', 'curators', 'cases',
        )

        # Add counts
        queryset = queryset.annotate(
            test_case_count=Count('cases'),
        )

        # Search filter
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search) | Q(name__icontains=search),
            )

        # Organization filter
        org_id = self.request.GET.get('organization')
        if org_id:
            try:
                queryset = queryset.filter(organization_id=int(org_id))
            except (ValueError, TypeError):
                pass

        return queryset.order_by('code')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get organizations where user is admin/member
        if self.request.user.is_authenticated:
            context['user_organizations'] = self.request.user.profile.organizations.all()

        context['search_query'] = self.request.GET.get('search', '')
        context['selected_org'] = self.request.GET.get('organization', '')

        return context


class DownloadProblemFullPackage(LoginRequiredMixin, ProblemDownloadMixin, View):
    """Download complete problem package: statement.pdf + tests.zip, all zipped together."""

    def get(self, request, *args, **kwargs):
        problem = self.get_problem(kwargs['problem'])

        try:
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:

                try:
                    self._add_pdf(zip_file, problem)
                except Exception as e:
                    zip_file.writestr('statement_error.txt', f'Unexpected error: {str(e)}')

                try:
                    data_files = getattr(problem, 'data_files', None)
                    if data_files and data_files.zipfile:
                        file_path = data_files.zipfile.name
                        file_basename = os.path.basename(file_path)

                        if problem_data_storage.exists(file_path):
                            with problem_data_storage.open(file_path, 'rb') as f:
                                zip_file.writestr(file_basename, f.read())
                        else:
                            zip_file.writestr('tests_error.txt', f'File recorded but not found on disk: {file_path}')
                except Exception as e:
                    zip_file.writestr('tests_error.txt', f'Error processing tests.zip: {str(e)}')

            response = HttpResponse(buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{problem.code}_package.zip"'
            return response

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def _add_pdf(self, zip_file, problem):
        """Fetch PDF from external URL and write to the zip file using its original filename."""
        if not problem.pdf_url:
            return

        try:
            parsed_url = urlparse(problem.pdf_url)
            filename = os.path.basename(parsed_url.path)

            response = requests.get(problem.pdf_url, timeout=10)
            response.raise_for_status()

            zip_file.writestr(filename, response.content)

        except requests.exceptions.RequestException as e:
            zip_file.writestr('statement_error.txt', f'Failed to download PDF ({problem.pdf_url}): {str(e)}')
