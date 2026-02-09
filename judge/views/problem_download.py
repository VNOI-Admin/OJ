import zipfile
from io import BytesIO

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
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

    @staticmethod
    def is_external_url(url):
        """Check if URL is external (http/https)"""
        return url.startswith('http://') or url.startswith('https://')

    @staticmethod
    def normalize_pdf_path(pdf_url):
        """Normalize PDF path by removing leading slash and media URL prefix"""
        pdf_path = pdf_url.lstrip('/')
        media_url = getattr(settings, 'MEDIA_URL', '/media/').lstrip('/')

        if pdf_path.startswith(media_url):
            pdf_path = pdf_path[len(media_url):]

        return pdf_path

    def add_pdf_to_zip(self, zip_file, problem, filename=None):
        """Add PDF to zip file if available, returns True if added, False otherwise"""
        if not problem.pdf_url:
            return False

        if self.is_external_url(problem.pdf_url):
            zip_file.writestr('statement_link.txt', f'PDF Statement URL: {problem.pdf_url}\n')
            return True

        pdf_path = self.normalize_pdf_path(problem.pdf_url)
        if not default_storage.exists(pdf_path):
            return False

        try:
            with default_storage.open(pdf_path, 'rb') as pdf_file:
                pdf_name = filename or f'{problem.code}_statement.pdf'
                zip_file.writestr(pdf_name, pdf_file.read())
            return True
        except Exception:
            return False

    @staticmethod
    def add_storage_file_to_zip(storage, zip_file, source_path, dest_name):
        """Add a file from storage to zip, returns True if added, False otherwise"""
        if not storage.exists(source_path):
            return False

        try:
            with storage.open(source_path, 'rb') as file_obj:
                zip_file.writestr(dest_name, file_obj.read())
            return True
        except Exception:
            return False

    @staticmethod
    def serve_file_from_storage(storage, file_path, filename, content_type='application/zip'):
        """Serve a file from storage as HTTP response"""
        if not storage.exists(file_path):
            return None

        try:
            with storage.open(file_path, 'rb') as file_obj:
                response = HttpResponse(file_obj.read(), content_type=content_type)
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception:
            return None


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


class DownloadProblemStatement(LoginRequiredMixin, ProblemDownloadMixin, View):
    """Download problem statement (PDF)"""

    def get(self, request, *args, **kwargs):
        problem = self.get_problem(kwargs['problem'])

        if not problem.pdf_url:
            return JsonResponse({'error': _('No PDF statement available')}, status=404)

        # If it's an external URL, redirect to it
        if self.is_external_url(problem.pdf_url):
            return redirect(problem.pdf_url)

        # Serve PDF from storage
        pdf_path = self.normalize_pdf_path(problem.pdf_url)

        if not default_storage.exists(pdf_path):
            return JsonResponse({'error': _('PDF statement file not found')}, status=404)

        try:
            with default_storage.open(pdf_path, 'rb') as pdf_file:
                response = HttpResponse(pdf_file.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{problem.code}_statement.pdf"'
            return response
        except Exception as e:
            return JsonResponse({'error': f'Error serving PDF: {str(e)}'}, status=500)


class DownloadProblemStatementZip(LoginRequiredMixin, ProblemDownloadMixin, View):
    """Download problem statement as a zip file (alternative format)"""

    def get(self, request, *args, **kwargs):
        problem = self.get_problem(kwargs['problem'])

        if not problem.pdf_url:
            return JsonResponse({'error': _('No PDF statement available')}, status=404)

        try:
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                if not self.add_pdf_to_zip(zip_file, problem):
                    return JsonResponse({'error': _('PDF statement file not found')}, status=404)

            response = HttpResponse(buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{problem.code}_statement.zip"'
            return response
        except Exception as e:
            return JsonResponse({'error': f'Error creating statement zip: {str(e)}'}, status=500)


class DownloadProblemTestData(LoginRequiredMixin, ProblemDownloadMixin, View):
    """Download problem test data as a zip file"""

    def get(self, request, *args, **kwargs):
        problem = self.get_problem(kwargs['problem'])

        if not hasattr(problem, 'data_files') or not problem.data_files:
            return JsonResponse({'error': _('No test data available')}, status=404)

        data_files = problem.data_files

        if not data_files.zipfile:
            return JsonResponse({'error': _('No test data zip file available')}, status=404)

        # Serve file using helper method
        response = self.serve_file_from_storage(
            problem_data_storage,
            data_files.zipfile.name,
            f'{problem.code}_tests.zip',
        )

        if response is None:
            return JsonResponse({'error': _('Test data file not found')}, status=404)

        return response


class DownloadProblemFullPackage(LoginRequiredMixin, ProblemDownloadMixin, View):
    """Download complete problem package including statement, tests, and metadata"""

    def get(self, request, *args, **kwargs):
        problem = self.get_problem(kwargs['problem'])

        try:
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr('metadata.txt', self._generate_metadata(problem))
                self.add_pdf_to_zip(zip_file, problem)

                if hasattr(problem, 'data_files') and problem.data_files and problem.data_files.zipfile:
                    self.add_storage_file_to_zip(
                        problem_data_storage, zip_file,
                        problem.data_files.zipfile.name, 'tests.zip',
                    )

                self.add_storage_file_to_zip(
                    problem_data_storage, zip_file,
                    f'{problem.code}/init.yml', 'init.yml',
                )

            response = HttpResponse(buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{problem.code}_full_package.zip"'
            return response
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def _generate_metadata(self, problem):
        """Generate metadata text file for the problem"""
        lines = [
            f'Problem Code: {problem.code}',
            f'Problem Name: {problem.name}',
            f'Time Limit: {problem.time_limit}s',
            f'Memory Limit: {problem.memory_limit}KB',
            f'Points: {problem.points}',
            f'Partial: {problem.partial}',
            '',
            f'Authors: {", ".join(author.user.username for author in problem.authors.all())}',
            f'Curators: {", ".join(curator.user.username for curator in problem.curators.all())}',
            '',
            f'Test Cases: {problem.cases.count()}',
        ]

        if problem.source:
            lines.insert(5, f'Source: {problem.source}')

        if problem.pdf_url:
            lines.append(f'PDF Statement URL: {problem.pdf_url}')

        return '\n'.join(lines)
