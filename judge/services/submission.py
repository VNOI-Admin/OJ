from dataclasses import dataclass
from typing import Any, Optional

from django.db.models import Case, IntegerField, Prefetch, QuerySet, Value, When

from judge.models import ProblemTranslation, Submission
from judge.repositories.submission import SubmissionListFilters, SubmissionRepository

@dataclass
class BadgeDTO:
    name: str
    mini: str

@dataclass
class ProfileDTO:
    id: int
    user_id: int
    user_username: str
    display_rank: str
    rating: Optional[int]
    username_display_override: str
    css_class: str
    display_name: str
    display_badge: Optional[BadgeDTO]
    
    @property
    def user(self):
        class _User:
            def __init__(self, username):
                self.username = username
        return _User(self.user_username)

@dataclass
class ProblemDTO:
    id: int
    code: str
    name: str
    i18n_name: str
    is_public: bool
    testcase_result_visibility_mode: str
    submission_source_visibility_mode: str
    submission_source_visibility: str
    is_suggesting: bool

@dataclass
class LanguageDTO:
    key: str
    short_name: str
    short_display_name: str
    file_only: bool

@dataclass
class ContestDTO:
    key: str
    name: str
    editor_ids: set

@dataclass
class SubmissionDTO:
    id: int
    result_class: str
    is_graded: bool
    status: str
    result: Optional[str]
    case_points: float
    case_total: float
    long_status: str
    short_status: str
    time: Optional[float]
    memory: Optional[float]
    date: Any
    current_testcase: int
    is_locked: bool
    language: LanguageDTO
    problem: ProblemDTO
    user: ProfileDTO
    contest_object: Optional[ContestDTO]
    contest_object_id: Optional[int]
    problem_id: int
    user_id: int


@dataclass
class SubmissionCursorPageResult:
    submissions: list
    has_previous: bool
    has_next: bool
    previous_position: Optional[int]
    next_position: Optional[int]


class SubmissionService:
    @classmethod
    def get_optimized_queryset(cls, queryset: QuerySet) -> QuerySet:
        qs = queryset.select_related(
            'user__user', 'user__display_badge', 'problem', 'language', 'contest_object'
        ).prefetch_related(
            'contest_object__authors', 'contest_object__curators'
        )
        
        only_fields = [
            'id', 'date', 'time', 'memory', 'points', 'result', 'status',
            'case_points', 'case_total', 'current_testcase', 'locked_after',
            'contest_object', 'contest_object__key', 'contest_object__name',
            'user__user__username', 'user__display_rank', 'user__rating', 
            'user__username_display_override', 'user__display_badge__name', 'user__display_badge__mini',
            'problem__name', 'problem__code', 'problem__is_public', 
            'problem__submission_source_visibility_mode', 'problem__testcase_result_visibility_mode',
            'problem__suggester', 
            'language__short_name', 'language__key', 'language__file_only',
        ]
        
        return qs.only(*only_fields)

    @classmethod
    def get_list_queryset(cls, ids, language_code=None):
        if not ids:
            return []

        ordering = Case(
            *(When(id=submission_id, then=Value(index)) for index, submission_id in enumerate(ids)),
            output_field=IntegerField(),
        )
        queryset = cls.get_optimized_queryset(Submission.objects.filter(id__in=ids)).order_by(ordering)
        if language_code is not None:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'problem__translations',
                    queryset=ProblemTranslation.objects.filter(language=language_code),
                    to_attr='_trans',
                ),
            )
        return list(queryset)

    @classmethod
    def get_result_counts(cls, request, filters):
        return SubmissionRepository(request, filters).fetch_result_counts()

    @classmethod
    def get_cursor_page(cls, request, filters, cursor, page_size, language_code=None):
        reverse = bool(cursor and cursor.reverse)
        position_id = cursor.position[0] if cursor is not None else None
        ids = SubmissionRepository(request, filters).fetch_cursor_ids(
            position_id=position_id,
            reverse=reverse,
            limit=page_size + 1,
        )
        has_more = len(ids) > page_size
        ids = ids[:page_size]
        if reverse:
            ids = list(reversed(ids))

        submissions = cls.get_list_queryset(ids, language_code)
        if not submissions:
            return SubmissionCursorPageResult(
                submissions=[],
                has_previous=False,
                has_next=False,
                previous_position=None,
                next_position=None,
            )

        if reverse:
            has_previous = has_more
            has_next = True
        else:
            has_previous = cursor is not None
            has_next = has_more

        return SubmissionCursorPageResult(
            submissions=submissions,
            has_previous=has_previous,
            has_next=has_next,
            previous_position=submissions[0].id if has_previous else None,
            next_position=submissions[-1].id if has_next else None,
        )

    @classmethod
    def map_to_dto(cls, sub, request_language_code=None) -> SubmissionDTO:
        badge_dto = None
        if getattr(sub.user, 'display_badge', None):
            badge_dto = BadgeDTO(
                name=sub.user.display_badge.name,
                mini=sub.user.display_badge.mini
            )
            
        profile_dto = ProfileDTO(
            id=sub.user.id,
            user_id=sub.user.user.id,
            user_username=sub.user.user.username,
            display_rank=sub.user.display_rank,
            rating=sub.user.rating,
            username_display_override=sub.user.username_display_override,
            css_class=sub.user.css_class,
            display_name=sub.user.display_name,
            display_badge=badge_dto
        )

        lang_dto = LanguageDTO(
            key=sub.language.key,
            short_name=sub.language.short_name,
            short_display_name=sub.language.short_display_name,
            file_only=sub.language.file_only
        )

        i18n_name = sub.problem.name
        if request_language_code:
            i18n_name = sub.problem.translated_name(request_language_code)
            
        is_suggesting = False
        if sub.problem.suggester_id is not None and not sub.problem.is_public:
            is_suggesting = True

        problem_dto = ProblemDTO(
            id=sub.problem.id,
            code=sub.problem.code,
            name=sub.problem.name,
            i18n_name=i18n_name,
            is_public=sub.problem.is_public,
            testcase_result_visibility_mode=sub.problem.testcase_result_visibility_mode,
            submission_source_visibility_mode=sub.problem.submission_source_visibility_mode,
            submission_source_visibility=sub.problem.submission_source_visibility,
            is_suggesting=is_suggesting
        )
        
        contest_dto = None
        if sub.contest_object_id and hasattr(sub, 'contest_object') and sub.contest_object is not None:
            # Evaluate related managers locally without SQL queries
            authors = [a.id for a in sub.contest_object.authors.all()]
            curators = [c.id for c in sub.contest_object.curators.all()]
            editor_ids = set(authors) | set(curators)
            contest_dto = ContestDTO(
                key=sub.contest_object.key,
                name=sub.contest_object.name,
                editor_ids=editor_ids
            )

        return SubmissionDTO(
            id=sub.id,
            result_class=sub.result_class,
            is_graded=sub.is_graded,
            status=sub.status,
            result=sub.result,
            case_points=sub.case_points,
            case_total=sub.case_total,
            long_status=sub.long_status,
            short_status=sub.short_status,
            time=sub.time,
            memory=sub.memory,
            date=sub.date,
            current_testcase=sub.current_testcase,
            is_locked=sub.is_locked,
            language=lang_dto,
            problem=problem_dto,
            user=profile_dto,
            contest_object=contest_dto,
            contest_object_id=sub.contest_object_id,
            problem_id=sub.problem.id,
            user_id=sub.user.id
        )


class RawSubmissionList:
    def __init__(self, request, filters, language_code=None):
        self.request = request
        self.filters = filters
        self.language_code = language_code

    def __getitem__(self, key):
        if isinstance(key, slice):
            if key.step not in (None, 1):
                raise ValueError('RawSubmissionList only supports contiguous slices.')
            offset = key.start or 0
            stop = key.stop
            if stop is None:
                raise ValueError('RawSubmissionList requires bounded slices.')
            return self._fetch(offset, max(stop - offset, 0))
        return self._fetch(key, 1)[0]

    def _fetch(self, offset, limit):
        ids = SubmissionRepository(self.request, self.filters).fetch_ids(offset, limit)
        return SubmissionService.get_list_queryset(ids, self.language_code)
