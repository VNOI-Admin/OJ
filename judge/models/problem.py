import errno
import json
from operator import attrgetter

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import CASCADE, F, Q, QuerySet, SET_NULL
from django.db.models.expressions import RawSQL
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from judge.fulltext import SearchQuerySet
from judge.models.problem_data import problem_data_storage
from judge.models.profile import Organization, Profile
from judge.models.runtime import Language
from judge.user_translations import gettext as user_gettext
from judge.utils.raw_sql import RawSQLColumn, unique_together_left_join

__all__ = ['ProblemGroup', 'ProblemType', 'Problem', 'ProblemTranslation', 'ProblemClarification', 'License',
           'Solution', 'SubmissionSourceAccess', 'TranslatedProblemQuerySet', 'TranslatedProblemForeignKeyQuerySet']


def disallowed_characters_validator(text):
    common_disallowed_characters = set(text) & settings.DMOJ_PROBLEM_STATEMENT_DISALLOWED_CHARACTERS
    if common_disallowed_characters:
        raise ValidationError(_('Disallowed characters: %(value)s'),
                              params={'value': ''.join(common_disallowed_characters)})


class ProblemType(models.Model):
    name = models.CharField(max_length=20, verbose_name=_('problem category ID'), unique=True)
    full_name = models.CharField(max_length=100, verbose_name=_('problem category name'))

    def __str__(self):
        return self.full_name

    class Meta:
        ordering = ['full_name']
        verbose_name = _('problem type')
        verbose_name_plural = _('problem types')


class ProblemGroup(models.Model):
    name = models.CharField(max_length=20, verbose_name=_('problem group ID'), unique=True)
    full_name = models.CharField(max_length=100, verbose_name=_('problem group name'))

    def __str__(self):
        return self.full_name

    class Meta:
        ordering = ['full_name']
        verbose_name = _('problem group')
        verbose_name_plural = _('problem groups')


class License(models.Model):
    key = models.CharField(max_length=20, unique=True, verbose_name=_('key'),
                           validators=[RegexValidator(r'^[-\w.]+$', r'License key must be ^[-\w.]+$')])
    link = models.CharField(max_length=256, verbose_name=_('link'))
    name = models.CharField(max_length=256, verbose_name=_('full name'))
    display = models.CharField(max_length=256, blank=True, verbose_name=_('short name'),
                               help_text=_('Displayed on pages under this license'))
    icon = models.CharField(max_length=256, blank=True, verbose_name=_('icon'), help_text=_('URL to the icon'))
    text = models.TextField(verbose_name=_('license text'))

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('license', args=(self.key,))

    class Meta:
        verbose_name = _('license')
        verbose_name_plural = _('licenses')


class TranslatedProblemQuerySet(SearchQuerySet):
    def __init__(self, **kwargs):
        super(TranslatedProblemQuerySet, self).__init__(('code', 'name', 'description'), **kwargs)

    def add_i18n_name(self, language):
        queryset = self._clone()
        alias = unique_together_left_join(queryset, ProblemTranslation, 'problem', 'language', language)
        return queryset.annotate(i18n_name=Coalesce(RawSQL('%s.name' % alias, ()), F('name'),
                                                    output_field=models.CharField()))


class TranslatedProblemForeignKeyQuerySet(QuerySet):
    def add_problem_i18n_name(self, key, language, name_field=None):
        queryset = self._clone() if name_field is None else self.annotate(_name=F(name_field))
        alias = unique_together_left_join(queryset, ProblemTranslation, 'problem', 'language', language,
                                          parent_model=Problem)
        # You must specify name_field if Problem is not yet joined into the QuerySet.
        kwargs = {key: Coalesce(RawSQL('%s.name' % alias, ()),
                                F(name_field) if name_field else RawSQLColumn(Problem, 'name'),
                                output_field=models.CharField())}
        return queryset.annotate(**kwargs)


class SubmissionSourceAccess:
    ALWAYS = 'A'
    SOLVED = 'S'
    ONLY_OWN = 'O'
    FOLLOW = 'F'


class ProblemTestcaseAccess:
    ALWAYS = 'A'
    OUT_CONTEST = 'C'
    AUTHOR_ONLY = 'O'


class ProblemTestcaseResultAccess:
    ALL_TEST_CASE = 'A'
    ONLY_BATCH_RESULT = 'B'
    ONLY_SUBMISSION_RESULT = 'S'


class Problem(models.Model):
    SUBMISSION_SOURCE_ACCESS = (
        (SubmissionSourceAccess.FOLLOW, _('Follow global setting')),
        (SubmissionSourceAccess.ALWAYS, _('Always visible')),
        (SubmissionSourceAccess.SOLVED, _('Visible if problem solved')),
        (SubmissionSourceAccess.ONLY_OWN, _('Only own submissions')),
    )

    PROBLEM_TESTCASE_ACCESS = (
        (ProblemTestcaseAccess.AUTHOR_ONLY, _('Visible for authors')),
        (ProblemTestcaseAccess.OUT_CONTEST, _('Visible if user is not in a contest')),
        (ProblemTestcaseAccess.ALWAYS, _('Always visible')),
    )

    PROBLEM_TESTCASE_RESULT_ACCESS = (
        (ProblemTestcaseResultAccess.ALL_TEST_CASE, _('Show all testcase result')),
        (ProblemTestcaseResultAccess.ONLY_BATCH_RESULT, _('Show batch result only')),
        (ProblemTestcaseResultAccess.ONLY_SUBMISSION_RESULT, _('Show submission result only')),
    )

    code = models.CharField(max_length=32, verbose_name=_('problem code'), unique=True,
                            validators=[RegexValidator('^[a-z0-9_]+$', _('Problem code must be ^[a-z0-9_]+$'))],
                            help_text=_('A short, unique code for the problem, '
                                        'used in the url after /problem/'))
    name = models.CharField(max_length=100, verbose_name=_('problem name'), db_index=True,
                            help_text=_('The full name of the problem, '
                                        'as shown in the problem list.'))
    pdf_url = models.CharField(max_length=200, verbose_name=_('PDF statement URL'), blank=True,
                               help_text=_('URL to PDF statement. The PDF file must be embeddable (Mobile web browsers'
                                           'may not support embedding). Fallback included.'))
    source = models.CharField(max_length=200, verbose_name=_('Problem source'), db_index=True, blank=True,
                              help_text=_('Source of problem. Please credit the source of the problem'
                                          'if it is not yours'))
    description = models.TextField(verbose_name=_('problem body'), blank=True,
                                   validators=[disallowed_characters_validator])
    authors = models.ManyToManyField(Profile, verbose_name=_('creators'), blank=True, related_name='authored_problems',
                                     help_text=_('These users will be able to edit the problem, '
                                                 'and be listed as authors.'))
    curators = models.ManyToManyField(Profile, verbose_name=_('curators'), blank=True, related_name='curated_problems',
                                      help_text=_('These users will be able to edit the problem, '
                                                  'but not be listed as authors.'))
    testers = models.ManyToManyField(Profile, verbose_name=_('testers'), blank=True, related_name='tested_problems',
                                     help_text=_(
                                         'These users will be able to view the private problem, but not edit it.'))
    types = models.ManyToManyField(ProblemType, verbose_name=_('problem types'),
                                   help_text=_('The type of problem, '
                                               "as shown on the problem's page."))
    group = models.ForeignKey(ProblemGroup, verbose_name=_('problem group'), on_delete=CASCADE,
                              help_text=_('The group of problem, shown under Category in the problem list.'))
    time_limit = models.FloatField(verbose_name=_('time limit'),
                                   help_text=_('The time limit for this problem, in seconds. '
                                               'Fractional seconds (e.g. 1.5) are supported.'),
                                   validators=[MinValueValidator(settings.DMOJ_PROBLEM_MIN_TIME_LIMIT),
                                               MaxValueValidator(settings.DMOJ_PROBLEM_MAX_TIME_LIMIT)])
    memory_limit = models.PositiveIntegerField(verbose_name=_('memory limit'),
                                               help_text=_('The memory limit for this problem, in kilobytes '
                                                           '(e.g. 64mb = 65536 kilobytes).'),
                                               validators=[MinValueValidator(settings.DMOJ_PROBLEM_MIN_MEMORY_LIMIT),
                                                           MaxValueValidator(settings.DMOJ_PROBLEM_MAX_MEMORY_LIMIT)])
    short_circuit = models.BooleanField(default=False)
    points = models.FloatField(verbose_name=_('points'),
                               help_text=_('Points awarded for problem completion. '
                                           "Points are displayed with a 'p' suffix if partial."),
                               validators=[MinValueValidator(settings.DMOJ_PROBLEM_MIN_PROBLEM_POINTS)])
    partial = models.BooleanField(verbose_name=_('allows partial points'), default=False)
    allowed_languages = models.ManyToManyField(Language, verbose_name=_('allowed languages'),
                                               help_text=_('List of allowed submission languages.'))
    is_public = models.BooleanField(verbose_name=_('publicly visible'), db_index=True, default=False)
    is_manually_managed = models.BooleanField(verbose_name=_('manually managed'), db_index=True, default=False,
                                              help_text=_('Whether judges should be allowed to manage data or not.'))
    date = models.DateTimeField(verbose_name=_('date of publishing'), null=True, blank=True, db_index=True,
                                help_text=_("Doesn't have magic ability to auto-publish due to backward compatibility"))
    banned_users = models.ManyToManyField(Profile, verbose_name=_('personae non gratae'), blank=True,
                                          help_text=_('Bans the selected users from submitting to this problem.'))
    license = models.ForeignKey(License, null=True, blank=True, on_delete=SET_NULL,
                                help_text=_('The license under which this problem is published.'))
    og_image = models.CharField(verbose_name=_('OpenGraph image'), max_length=150, blank=True)
    summary = models.TextField(blank=True, verbose_name=_('problem summary'),
                               help_text=_('Plain-text, shown in meta description tag, e.g. for social media.'))
    user_count = models.IntegerField(verbose_name=_('number of users'), default=0,
                                     help_text=_('The number of users who solved the problem.'))
    ac_rate = models.FloatField(verbose_name=_('solve rate'), default=0)
    is_full_markup = models.BooleanField(verbose_name=_('allow full markdown access'), default=False)
    submission_source_visibility_mode = models.CharField(verbose_name=_('submission source visibility'), max_length=1,
                                                         default=SubmissionSourceAccess.FOLLOW,
                                                         choices=SUBMISSION_SOURCE_ACCESS)
    testcase_visibility_mode = models.CharField(verbose_name=_('Testcase visibility'), max_length=1,
                                                default=ProblemTestcaseAccess.AUTHOR_ONLY,
                                                choices=PROBLEM_TESTCASE_ACCESS)

    testcase_result_visibility_mode = models.CharField(verbose_name=_('Testcase result visibility'), max_length=1,
                                                       default=ProblemTestcaseResultAccess.ALL_TEST_CASE,
                                                       choices=PROBLEM_TESTCASE_RESULT_ACCESS,
                                                       help_text=_('What testcase result should be showed to users?'))

    objects = TranslatedProblemQuerySet.as_manager()
    tickets = GenericRelation('Ticket')

    organizations = models.ManyToManyField(Organization, blank=True, verbose_name=_('organizations'),
                                           help_text=_('If private, only these organizations may see the problem.'))
    is_organization_private = models.BooleanField(verbose_name=_('private to organizations'), default=False)

    suggester = models.ForeignKey(Profile, blank=True, null=True, related_name='suggested_problems', on_delete=SET_NULL)

    allow_view_feedback = models.BooleanField(
        help_text=_('Allow user to view checker feedback.'),
        default=False,
    )

    __original_points = None

    def __init__(self, *args, **kwargs):
        super(Problem, self).__init__(*args, **kwargs)
        self._translated_name_cache = {}
        self._i18n_name = None
        self.__original_code = self.code
        # Since `points` may get defer()
        # We only set original points it is not deferred
        if 'points' in self.__dict__:
            self.__original_points = self.points

    @cached_property
    def types_list(self):
        return list(map(user_gettext, map(attrgetter('full_name'), self.types.all())))

    def languages_list(self):
        return self.allowed_languages.values_list('common_name', flat=True).distinct().order_by('common_name')

    def is_editor(self, profile):
        return (self.authors.filter(id=profile.id) | self.curators.filter(id=profile.id)).exists()

    @property
    def is_suggesting(self):
        return self.suggester is not None and not self.is_public

    def is_editable_by(self, user):
        if not user.is_authenticated:
            return False
        if not user.has_perm('judge.edit_own_problem'):
            return False
        if user.has_perm('judge.suggest_new_problem') and self.is_suggesting:
            return True
        if user.has_perm('judge.edit_all_problem') or user.has_perm('judge.edit_public_problem') and self.is_public:
            return True
        if user.profile.id in self.editor_ids:
            return True
        return False

    def is_accessible_by(self, user, skip_contest_problem_check=False):
        # If we don't want to check if the user is in a contest containing that problem.
        if not skip_contest_problem_check and user.is_authenticated:
            # If user is currently in a contest containing that problem.
            current = user.profile.current_contest_id
            if current is not None:
                from judge.models import ContestProblem
                if ContestProblem.objects.filter(problem_id=self.id, contest__users__id=current).exists():
                    return True

        # Problem is public.
        if self.is_public and not self.is_suggesting:
            # Problem is not private to an organization.
            if not self.is_organization_private:
                return True

            # If the user can see all organization private problems.
            if user.has_perm('judge.see_organization_problem'):
                return True

            # If the user is in the organization.
            if user.is_authenticated and \
                    self.organizations.filter(id__in=user.profile.organizations.all()):
                return True

        if not user.is_authenticated:
            return False

        # If the user can view all problems.
        if user.has_perm('judge.see_private_problem'):
            return True

        # If the user can edit the problem.
        # We are using self.editor_ids to take advantage of caching.
        if self.is_editable_by(user) or user.profile.id in self.editor_ids:
            return True

        # If user is a suggester
        if user.has_perm('judge.suggest_new_problem') and self.is_suggesting:
            return True

        # If user is a tester.
        if self.testers.filter(id=user.profile.id).exists():
            return True

        return False

    def is_rejudgeable_by(self, user):
        return user.has_perm('judge.rejudge_submission') and self.is_editable_by(user)

    def is_subs_manageable_by(self, user):
        return user.is_staff and self.is_rejudgeable_by(user)

    def is_testcase_accessible_by(self, user):
        if self.testcase_visibility_mode == ProblemTestcaseAccess.ALWAYS:
            return True

        if not user.is_authenticated:
            return False

        if self.is_editable_by(user):
            return True

        if self.testcase_visibility_mode == ProblemTestcaseAccess.OUT_CONTEST:
            return user.profile.current_contest is None

        # Don't need to check for ProblemTestcaseAccess.AUTHOR_ONLY
        return False

    @classmethod
    def get_visible_problems(cls, user):
        # Do unauthenticated check here so we can skip authentication checks later on.
        if not user.is_authenticated:
            return cls.get_public_problems()

        # Conditions for visible problem:
        #   - `judge.edit_all_problem` or `judge.see_private_problem`
        #   - otherwise
        #       - not is_public problems
        #           - author or curator or tester
        #           - is_organization_private and admin of organization
        #           - is_suggesting and user is a suggester
        #       - is_public problems
        #           - not is_organization_private or in organization or `judge.see_organization_problem`
        #           - author or curator or tester
        queryset = cls.objects.defer('description')

        edit_own_problem = user.has_perm('judge.edit_own_problem')
        edit_public_problem = edit_own_problem and user.has_perm('judge.edit_public_problem')
        edit_all_problem = edit_own_problem and user.has_perm('judge.edit_all_problem')
        edit_suggesting_problem = edit_own_problem and user.has_perm('judge.suggest_new_problem')

        if not (user.has_perm('judge.see_private_problem') or edit_all_problem):
            q = Q(is_public=True)
            if not (user.has_perm('judge.see_organization_problem') or edit_public_problem):
                # Either not organization private or in the organization.
                q &= (
                    Q(is_organization_private=False) |
                    Q(is_organization_private=True, organizations__in=user.profile.organizations.all())
                )

            # Suggesters should be able to view suggesting problems
            if edit_suggesting_problem:
                q |= Q(suggester__isnull=False, is_public=False)

            # Authors, curators, and testers should always have access, so OR at the very end.
            q |= Q(authors=user.profile)
            q |= Q(curators=user.profile)
            q |= Q(testers=user.profile)
            queryset = queryset.filter(q)

        return queryset

    @classmethod
    def get_public_problems(cls):
        return cls.objects.filter(is_public=True, is_organization_private=False).defer('description')

    @classmethod
    def get_editable_problems(cls, user):
        if not user.has_perm('judge.edit_own_problem'):
            return cls.objects.none()
        if user.has_perm('judge.edit_all_problem'):
            return cls.objects.all()

        q = Q(authors=user.profile) | Q(curators=user.profile) | Q(suggester=user.profile)

        if user.has_perm('judge.edit_public_problem'):
            q |= Q(is_public=True)
        if user.has_perm('judge.suggest_new_problem'):
            q |= Q(suggester__isnull=False, is_public=False)

        return cls.objects.filter(q)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('problem_detail', args=(self.code,))

    @cached_property
    def author_ids(self):
        return Problem.authors.through.objects.filter(problem=self).values_list('profile_id', flat=True)

    @cached_property
    def editor_ids(self):
        editors = self.author_ids.union(
            Problem.curators.through.objects.filter(problem=self).values_list('profile_id', flat=True))
        if self.suggester is not None:
            editors = list(editors)
            editors.append(self.suggester.id)
        return editors

    @cached_property
    def tester_ids(self):
        return Problem.testers.through.objects.filter(problem=self).values_list('profile_id', flat=True)

    @cached_property
    def usable_common_names(self):
        return set(self.usable_languages.values_list('common_name', flat=True))

    @property
    def usable_languages(self):
        return self.allowed_languages.filter(judges__in=self.judges.filter(online=True)).distinct()

    def translated_name(self, language):
        if language in self._translated_name_cache:
            return self._translated_name_cache[language]
        # Hits database despite prefetch_related.
        try:
            name = self.translations.filter(language=language).values_list('name', flat=True)[0]
        except IndexError:
            name = self.name
        self._translated_name_cache[language] = name
        return name

    @property
    def i18n_name(self):
        if self._i18n_name is None:
            self._i18n_name = self._trans[0].name if self._trans else self.name
        return self._i18n_name

    @i18n_name.setter
    def i18n_name(self, value):
        self._i18n_name = value

    @property
    def clarifications(self):
        return ProblemClarification.objects.filter(problem=self)

    @cached_property
    def submission_source_visibility(self):
        if self.submission_source_visibility_mode == SubmissionSourceAccess.FOLLOW:
            return {
                'all': SubmissionSourceAccess.ALWAYS,
                'all-solved': SubmissionSourceAccess.SOLVED,
                'only-own': SubmissionSourceAccess.ONLY_OWN,
            }[settings.DMOJ_SUBMISSION_SOURCE_VISIBILITY]
        return self.submission_source_visibility_mode

    def update_stats(self):
        all_queryset = self.submission_set.filter(user__is_unlisted=False)
        ac_queryset = all_queryset.filter(points__gte=self.points, result='AC')
        self.user_count = ac_queryset.values('user').distinct().count()
        submissions = all_queryset.count()
        if submissions:
            self.ac_rate = 100.0 * ac_queryset.count() / submissions
        else:
            self.ac_rate = 0
        self.save()

    update_stats.alters_data = True

    def _get_limits(self, key):
        global_limit = getattr(self, key)
        limits = {limit['language_id']: (limit['language__name'], limit[key])
                  for limit in self.language_limits.values('language_id', 'language__name', key)
                  if limit[key] != global_limit}
        limit_ids = set(limits.keys())
        common = []

        for cn, ids in Language.get_common_name_map().items():
            if ids - limit_ids:
                continue
            limit = set(limits[id][1] for id in ids)
            if len(limit) == 1:
                limit = next(iter(limit))
                common.append((cn, limit))
                for id in ids:
                    del limits[id]

        limits = list(limits.values()) + common
        limits.sort()
        return limits

    @property
    def language_time_limit(self):
        key = 'problem_tls:%d' % self.id
        result = cache.get(key)
        if result is not None:
            return result
        result = self._get_limits('time_limit')
        cache.set(key, result)
        return result

    @property
    def language_memory_limit(self):
        key = 'problem_mls:%d' % self.id
        result = cache.get(key)
        if result is not None:
            return result
        result = self._get_limits('memory_limit')
        cache.set(key, result)
        return result

    @property
    def markdown_style(self):
        return 'problem-full' if self.is_full_markup else 'problem'

    @cached_property
    def io_method(self):
        if self.is_manually_managed or not hasattr(self, 'data_files'):
            return {'method': 'unknown'}

        if self.data_files.grader != 'standard':
            # File IO is only supported for the standard grader.
            return {'method': 'standard'}

        grader_args = self.data_files.grader_args
        if grader_args:
            grader_args = json.loads(grader_args)
            if grader_args.get('io_method', '') == 'file':
                if grader_args.get('io_input_file', '') == '' or grader_args.get('io_output_file', '') == '':
                    return {'method': 'unknown'}

                return {
                    'method': 'file',
                    'input': grader_args['io_input_file'],
                    'output': grader_args['io_output_file'],
                }

        return {'method': 'standard'}

    def save(self, *args, **kwargs):
        is_clone = kwargs.pop('is_clone', False)
        # if short_circuit = true the judge will stop judging
        # as soon as the submission failed a test case
        self.short_circuit = not self.partial
        super(Problem, self).save(*args, **kwargs)
        # Ignore the custom save if we are cloning a problem
        if is_clone:
            return
        if self.code != self.__original_code:
            try:
                problem_data = self.data_files
            except AttributeError:
                # On create, self.__original_code is an empty string
                if self.__original_code:
                    try:
                        problem_data_storage.rename(self.__original_code, self.code)
                    except OSError as e:
                        if e.errno != errno.ENOENT:
                            raise
            else:
                problem_data._update_code(self.__original_code, self.code)
            # Now the instance is saved, we need to update the original code to
            # new code so that if the user uses .save() multiple time, it will not run
            # update_code() multiple time
            self.__original_code = self.code

        # self.__original_points will be None if:
        #   - create new instance (should ignore)
        #   - The `points` field got deferred (not sure about this?)
        # in both cases, we don't rescore submissions.
        if self.__original_points is not None and self.points != self.__original_points:
            self._rescore()
            # same reason as update __original_code
            self.__original_points = self.points

    save.alters_data = True

    def _rescore(self):
        from judge.tasks import rescore_problem
        transaction.on_commit(rescore_problem.s(self.id, False).delay)

    class Meta:
        permissions = (
            ('see_private_problem', _('See hidden problems')),
            ('edit_own_problem', _('Edit own problems')),
            ('create_organization_problem', _('Create organization problem')),
            ('edit_all_problem', _('Edit all problems')),
            ('edit_public_problem', _('Edit all public problems')),
            ('suggest_new_problem', _('Suggest new problem')),
            ('problem_full_markup', _('Edit problems with full markup')),
            ('clone_problem', _('Clone problem')),
            ('upload_file_statement', _('Upload file-type statement')),
            ('change_public_visibility', _('Change is_public field')),
            ('change_manually_managed', _('Change is_manually_managed field')),
            ('see_organization_problem', _('See organization-private problems')),
        )
        verbose_name = _('problem')
        verbose_name_plural = _('problems')


class ProblemTranslation(models.Model):
    problem = models.ForeignKey(Problem, verbose_name=_('problem'), related_name='translations', on_delete=CASCADE)
    language = models.CharField(verbose_name=_('language'), max_length=7, choices=settings.LANGUAGES)
    name = models.CharField(verbose_name=_('translated name'), max_length=100, db_index=True)
    description = models.TextField(verbose_name=_('translated description'),
                                   validators=[disallowed_characters_validator])

    class Meta:
        unique_together = ('problem', 'language')
        verbose_name = _('problem translation')
        verbose_name_plural = _('problem translations')


class ProblemClarification(models.Model):
    problem = models.ForeignKey(Problem, verbose_name=_('clarified problem'), on_delete=CASCADE)
    description = models.TextField(verbose_name=_('clarification body'), validators=[disallowed_characters_validator])
    date = models.DateTimeField(verbose_name=_('clarification timestamp'), auto_now_add=True)


class LanguageLimit(models.Model):
    problem = models.ForeignKey(Problem, verbose_name=_('problem'), related_name='language_limits', on_delete=CASCADE)
    language = models.ForeignKey(Language, verbose_name=_('language'), on_delete=CASCADE)
    time_limit = models.FloatField(verbose_name=_('time limit'),
                                   validators=[MinValueValidator(settings.DMOJ_PROBLEM_MIN_TIME_LIMIT),
                                               MaxValueValidator(settings.DMOJ_PROBLEM_MAX_TIME_LIMIT)])
    memory_limit = models.IntegerField(verbose_name=_('memory limit'),
                                       validators=[MinValueValidator(settings.DMOJ_PROBLEM_MIN_MEMORY_LIMIT),
                                                   MaxValueValidator(settings.DMOJ_PROBLEM_MAX_MEMORY_LIMIT)])

    class Meta:
        unique_together = ('problem', 'language')
        verbose_name = _('language-specific resource limit')
        verbose_name_plural = _('language-specific resource limits')


class Solution(models.Model):
    problem = models.OneToOneField(Problem, on_delete=SET_NULL, verbose_name=_('associated problem'),
                                   null=True, blank=True, related_name='solution')
    is_public = models.BooleanField(verbose_name=_('public visibility'), default=False)
    publish_on = models.DateTimeField(verbose_name=_('publish date'))
    authors = models.ManyToManyField(Profile, verbose_name=_('authors'), blank=True)
    content = models.TextField(verbose_name=_('editorial content'), validators=[disallowed_characters_validator])

    def get_absolute_url(self):
        problem = self.problem
        if problem is None:
            return reverse('home')
        else:
            return reverse('problem_editorial', args=[problem.code])

    def __str__(self):
        return _('Editorial for %s') % self.problem.name

    def is_accessible_by(self, user):
        if self.is_public and self.publish_on < timezone.now():
            return True
        if user.has_perm('judge.see_private_solution'):
            return True
        if self.problem.is_editable_by(user):
            return True
        return False

    class Meta:
        permissions = (
            ('see_private_solution', _('See hidden solutions')),
        )
        verbose_name = _('solution')
        verbose_name_plural = _('solutions')
