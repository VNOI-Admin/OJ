from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from django.db import connection
from django.utils import timezone

from judge.models import Contest, Submission


@dataclass(frozen=True)
class SubmissionListFilters:
    languages: frozenset
    statuses: frozenset
    organization_id: Optional[int] = None


class SubmissionRepository:
    def __init__(self, request, filters):
        self.request = request
        self.filters = filters
        self.user = request.user
        self.profile_id = request.profile.id if request.user.is_authenticated else None

    def fetch_ids(self, offset, limit):
        if limit <= 0:
            return []

        status_clauses = self._status_filter_clauses()
        if len(status_clauses) > 1:
            base_where, base_params = self._where_sql(include_status=False)
            sql, params = self._status_union_ids_sql(
                base_where=base_where,
                base_params=base_params,
                status_clauses=status_clauses,
                extra_where=[],
                extra_params=[],
                order_direction='DESC',
                branch_limit=offset + limit,
                final_limit=limit,
                final_offset=offset,
            )
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [row[0] for row in cursor.fetchall()]

        where, params = self._where_sql()
        sql = '''
            SELECT {optimizer_hint} s.id
            FROM judge_submission s {submission_index_hint}
            JOIN judge_problem p ON p.id = s.problem_id
            {language_join}
            {organization_join}
            WHERE {where}
            ORDER BY s.id DESC
            LIMIT %s OFFSET %s
        '''.format(
            optimizer_hint=self._optimizer_hint(),
            submission_index_hint=self._submission_index_hint(),
            language_join=self._language_join_sql(),
            organization_join=self._organization_join_sql(),
            where=' AND '.join(where),
        )
        params.extend([limit, offset])
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return [row[0] for row in cursor.fetchall()]

    def fetch_cursor_ids(self, position_id, reverse, limit):
        if limit <= 0:
            return []

        extra_where = []
        extra_params = []
        cursor_sql, cursor_params = self._cursor_filter_sql(position_id, reverse)
        if cursor_sql is not None:
            extra_where.append(cursor_sql)
            extra_params.extend(cursor_params)

        order_direction = 'ASC' if reverse else 'DESC'
        status_clauses = self._status_filter_clauses()
        if len(status_clauses) > 1:
            base_where, base_params = self._where_sql(include_status=False)
            sql, params = self._status_union_ids_sql(
                base_where=base_where,
                base_params=base_params,
                status_clauses=status_clauses,
                extra_where=extra_where,
                extra_params=extra_params,
                order_direction=order_direction,
                branch_limit=limit,
                final_limit=limit,
            )
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [row[0] for row in cursor.fetchall()]

        where, params = self._where_sql()
        where.extend(extra_where)
        params.extend(extra_params)

        sql = '''
            SELECT {optimizer_hint} s.id
            FROM judge_submission s {submission_index_hint}
            JOIN judge_problem p ON p.id = s.problem_id
            {language_join}
            {organization_join}
            WHERE {where}
            ORDER BY s.id {order_direction}
            LIMIT %s
        '''.format(
            optimizer_hint=self._optimizer_hint(),
            submission_index_hint=self._submission_index_hint(),
            language_join=self._language_join_sql(),
            organization_join=self._organization_join_sql(),
            where=' AND '.join(where),
            order_direction=order_direction,
        )
        params.append(limit)
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return [row[0] for row in cursor.fetchall()]

    def fetch_result_counts(self):
        status_clauses = self._status_filter_clauses()
        if len(status_clauses) > 1:
            base_where, base_params = self._where_sql(include_status=False)
            sql, params = self._status_union_result_counts_sql(
                base_where=base_where,
                base_params=base_params,
                status_clauses=status_clauses,
            )
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return defaultdict(int, cursor.fetchall())

        where, params = self._where_sql()
        sql = '''
            SELECT {optimizer_hint} s.result, COUNT(s.result)
            FROM judge_submission s
            JOIN judge_problem p ON p.id = s.problem_id
            {language_join}
            {organization_join}
            WHERE {where}
            GROUP BY s.result
        '''.format(
            optimizer_hint=self._optimizer_hint(),
            language_join=self._language_join_sql(),
            organization_join=self._organization_join_sql(),
            where=' AND '.join(where),
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return defaultdict(int, cursor.fetchall())

    def _where_sql(self, include_status=True):
        where = []
        params = []

        problem_sql, problem_params = self._visible_problem_sql()
        where.append(problem_sql)
        params.extend(problem_params)

        contest_sql, contest_params = self._visible_contest_sql()
        where.append(contest_sql)
        params.extend(contest_params)

        if self.filters.languages:
            where.append('l.key IN ({})'.format(self._placeholders(self.filters.languages)))
            params.extend(sorted(self.filters.languages))

        if include_status and self.filters.statuses:
            status_clauses = self._status_filter_clauses()
            if not status_clauses:
                where.append('0 = 1')
            elif len(status_clauses) == 1:
                status_sql, status_params = status_clauses[0]
                where.append(status_sql)
                params.extend(status_params)
            else:
                where.append('({})'.format(' OR '.join(sql for sql, _ in status_clauses)))
                for _, status_params in status_clauses:
                    params.extend(status_params)

        if self.filters.organization_id is not None:
            where.append('profile_organizations.organization_id = %s')
            params.append(self.filters.organization_id)

        return where, params

    def _cursor_filter_sql(self, position_id, reverse):
        if position_id is None:
            return None, []
        return ('s.id > %s' if reverse else 's.id < %s'), [position_id]

    def _status_filter_clauses(self):
        if not self.filters.statuses:
            return []

        selected = set(self.filters.statuses)
        result_codes = {code for code, _ in Submission.RESULT}
        status_codes = {code for code, _ in Submission.STATUS}

        clauses = []
        result_values = sorted(selected & result_codes)
        if result_values:
            clauses.append((
                's.result IN ({})'.format(self._placeholders(result_values)),
                result_values,
            ))

        if self._could_filter_by_status():
            status_values = sorted(selected & status_codes)
            if status_values:
                clauses.append((
                    's.status IN ({})'.format(self._placeholders(status_values)),
                    status_values,
                ))

        return clauses

    def _status_union_ids_sql(
            self,
            base_where,
            base_params,
            status_clauses,
            extra_where,
            extra_params,
            order_direction,
            branch_limit,
            final_limit,
            final_offset=None):
        branch_sql = []
        params = []

        for index, (status_sql, status_params) in enumerate(status_clauses):
            where = list(base_where) + [status_sql] + list(extra_where)
            branch_sql.append('''
                SELECT id
                FROM (
                    SELECT {optimizer_hint} s.id AS id
                    FROM judge_submission s {submission_index_hint}
                    JOIN judge_problem p ON p.id = s.problem_id
                    {language_join}
                    {organization_join}
                    WHERE {where}
                    ORDER BY s.id {order_direction}
                    LIMIT %s
                ) status_branch_{index}
            '''.format(
                optimizer_hint=self._optimizer_hint(),
                submission_index_hint=self._submission_index_hint(),
                language_join=self._language_join_sql(),
                organization_join=self._organization_join_sql(),
                where=' AND '.join(where),
                order_direction=order_direction,
                index=index,
            ))
            params.extend(base_params)
            params.extend(status_params)
            params.extend(extra_params)
            params.append(branch_limit)

        offset_sql = ''
        if final_offset is not None:
            offset_sql = ' OFFSET %s'

        sql = '''
            SELECT id
            FROM (
                {union_sql}
            ) status_union
            ORDER BY id {order_direction}
            LIMIT %s{offset_sql}
        '''.format(
            union_sql=' UNION '.join(branch_sql),
            order_direction=order_direction,
            offset_sql=offset_sql,
        )
        params.append(final_limit)
        if final_offset is not None:
            params.append(final_offset)
        return sql, params

    def _status_union_result_counts_sql(self, base_where, base_params, status_clauses):
        branch_sql = []
        params = []

        for status_sql, status_params in status_clauses:
            where = list(base_where) + [status_sql]
            branch_sql.append('''
                SELECT {optimizer_hint} s.id AS id, s.result AS result
                FROM judge_submission s
                JOIN judge_problem p ON p.id = s.problem_id
                {language_join}
                {organization_join}
                WHERE {where}
            '''.format(
                optimizer_hint=self._optimizer_hint(),
                language_join=self._language_join_sql(),
                organization_join=self._organization_join_sql(),
                where=' AND '.join(where),
            ))
            params.extend(base_params)
            params.extend(status_params)

        sql = '''
            SELECT result, COUNT(result)
            FROM (
                {union_sql}
            ) status_union
            GROUP BY result
        '''.format(union_sql=' UNION '.join(branch_sql))
        return sql, params

    def _visible_problem_sql(self):
        where = ['p.deleted_at IS NULL']
        params = []

        if not self.user.is_authenticated:
            where.append('p.is_public = %s')
            where.append('p.is_organization_private = %s')
            params.extend([True, False])
            return '({})'.format(' AND '.join(where)), params

        edit_own_problem = self.user.has_perm('judge.edit_own_problem')
        edit_public_problem = edit_own_problem and self.user.has_perm('judge.edit_public_problem')
        edit_all_problem = edit_own_problem and self.user.has_perm('judge.edit_all_problem')
        edit_suggesting_problem = edit_own_problem and self.user.has_perm('judge.suggest_new_problem')

        if self.user.has_perm('judge.see_private_problem') or edit_all_problem:
            return '({})'.format(' AND '.join(where)), params

        visibility_sql = ['p.is_public = %s']
        visibility_params = [True]

        if not (self.user.has_perm('judge.see_organization_problem') or edit_public_problem):
            organization_membership = '''
                EXISTS (
                    SELECT 1
                    FROM judge_profile_organizations po
                    WHERE po.profile_id = %s
                      AND po.organization_id = p.organization_id
                )
            '''
            visibility_sql[0] = '({} AND (p.is_organization_private = %s OR {}))'.format(
                visibility_sql[0],
                organization_membership,
            )
            visibility_params.extend([False, self.profile_id])

        if edit_suggesting_problem:
            visibility_sql.append('(p.suggester_id IS NOT NULL AND p.is_public = %s)')
            visibility_params.append(False)

        visibility_sql.extend([
            self._exists_problem_author_sql(),
            self._exists_problem_curator_sql(),
            self._exists_problem_tester_sql(),
        ])
        visibility_params.extend([self.profile_id, self.profile_id, self.profile_id])

        where.append('({})'.format(' OR '.join(visibility_sql)))
        params.extend(visibility_params)
        return '({})'.format(' AND '.join(where)), params

    def _visible_contest_sql(self):
        if self.user.has_perm('judge.see_private_contest'):
            return '(1 = 1)', []

        def contest_visibility_sql(editor_sql):
            return '''
                EXISTS (
                    SELECT 1
                    FROM judge_contest c
                    WHERE c.id = s.contest_object_id
                      AND ({editor_sql}
                           OR c.scoreboard_visibility = %s
                           OR c.end_time < %s)
                )
            '''.format(editor_sql=editor_sql)

        if not self.user.is_authenticated:
            anonymous_editor_sql = ' OR '.join([
                self._not_exists_contest_author_sql(),
                self._not_exists_contest_curator_sql(),
            ])
            return '''
                (
                    s.contest_object_id IS NULL
                    OR {contest_visibility_sql}
                )
            '''.format(contest_visibility_sql=contest_visibility_sql(anonymous_editor_sql)), [
                Contest.SCOREBOARD_VISIBLE,
                timezone.now(),
            ]

        editor_sql = ' OR '.join([
            self._exists_contest_author_sql(),
            self._exists_contest_curator_sql(),
        ])
        contest_sql = '''
            (
                s.user_id = %s
                OR s.contest_object_id IS NULL
                OR {contest_visibility_sql}
            )
        '''.format(contest_visibility_sql=contest_visibility_sql(editor_sql))
        return contest_sql, [
            self.profile_id,
            self.profile_id,
            self.profile_id,
            Contest.SCOREBOARD_VISIBLE,
            timezone.now(),
        ]

    def _organization_join_sql(self):
        if self.filters.organization_id is None:
            return ''
        return 'JOIN judge_profile_organizations profile_organizations ON profile_organizations.profile_id = s.user_id'

    def _language_join_sql(self):
        if not self.filters.languages:
            return ''
        return 'JOIN judge_language l ON l.id = s.language_id'

    def _optimizer_hint(self):
        if connection.vendor == 'mysql':
            return '/*+ JOIN_FIXED_ORDER() */'
        return ''

    def _submission_index_hint(self):
        if connection.vendor != 'mysql':
            return ''
        if self._can_scan_submission_first():
            return 'FORCE INDEX (PRIMARY)'
        return ''

    def _can_scan_submission_first(self):
        return not self.filters.languages and not self.filters.statuses and self.filters.organization_id is None

    def _exists_problem_author_sql(self):
        return '''
            EXISTS (
                SELECT 1
                FROM judge_problem_authors pe
                WHERE pe.problem_id = p.id
                  AND pe.profile_id = %s
            )
        '''

    def _exists_problem_curator_sql(self):
        return '''
            EXISTS (
                SELECT 1
                FROM judge_problem_curators pe
                WHERE pe.problem_id = p.id
                  AND pe.profile_id = %s
            )
        '''

    def _exists_problem_tester_sql(self):
        return '''
            EXISTS (
                SELECT 1
                FROM judge_problem_testers pe
                WHERE pe.problem_id = p.id
                  AND pe.profile_id = %s
            )
        '''

    def _exists_contest_author_sql(self):
        return '''
            EXISTS (
                SELECT 1
                FROM judge_contest_authors ce
                WHERE ce.contest_id = c.id
                  AND ce.profile_id = %s
            )
        '''

    def _exists_contest_curator_sql(self):
        return '''
            EXISTS (
                SELECT 1
                FROM judge_contest_curators ce
                WHERE ce.contest_id = c.id
                  AND ce.profile_id = %s
            )
        '''

    def _not_exists_contest_author_sql(self):
        return '''
            NOT EXISTS (
                SELECT 1
                FROM judge_contest_authors ce
                WHERE ce.contest_id = c.id
            )
        '''

    def _not_exists_contest_curator_sql(self):
        return '''
            NOT EXISTS (
                SELECT 1
                FROM judge_contest_curators ce
                WHERE ce.contest_id = c.id
            )
        '''

    def _could_filter_by_status(self):
        return self.user.is_superuser or self.user.is_staff

    def _placeholders(self, values):
        return ', '.join(['%s'] * len(values))
