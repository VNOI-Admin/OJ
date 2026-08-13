from django.test import SimpleTestCase

from judge.bridge.judge_handler import SubmissionUnavailable
from judge.bridge.judge_list import JudgeList
from judge.judge_priority import DEFAULT_PRIORITY


class MockJudge:
    def __init__(self, name, vanished=()):
        self.name = name
        self.tier = 0
        self.load = 0
        self.is_disabled = False
        self.problems = {'problem'}
        self.executors = {'lang'}
        self.submissions = []
        self._working = False
        self._vanished = set(vanished)

    @property
    def working(self):
        return bool(self._working)

    def can_judge(self, problem, executor, judge_id=None):
        return problem in self.problems and executor in self.executors and \
            ((not judge_id and not self.is_disabled) or self.name == judge_id)

    def get_current_submission(self):
        return self._working or None

    def submit(self, id, problem, language, source):
        if id in self._vanished:
            raise SubmissionUnavailable('submission %s vanished before it could be dispatched' % id)
        self._working = id
        self.submissions.append(id)

    def disconnect(self, force=False):
        pass


class JudgeListVanishedSubmissionTestCase(SimpleTestCase):
    def setUp(self):
        self.judges = JudgeList()

    def submit(self, id):
        self.judges.judge(id, 'problem', 'lang', 'source', None, DEFAULT_PRIORITY)

    def test_vanished_submission_is_dropped_without_blaming_the_judge(self):
        judge = MockJudge('judge', vanished={1})
        self.judges.register(judge)

        self.submit(1)

        self.assertEqual(judge.submissions, [])
        self.assertNotIn(1, self.judges.submission_map)
        self.assertNotIn(1, self.judges.node_map)
        self.assertIn(judge, self.judges.judges)

    def test_judge_is_still_usable_after_a_submission_vanishes(self):
        judge = MockJudge('judge', vanished={1})
        self.judges.register(judge)

        self.submit(1)
        self.submit(2)

        self.assertEqual(judge.submissions, [2])
        self.assertEqual(self.judges.submission_map[2], judge)

    def test_vanished_queued_submission_is_dropped(self):
        judge = MockJudge('judge', vanished={2})
        self.judges.register(judge)

        self.submit(1)
        self.submit(2)
        self.submit(3)
        self.assertEqual(sorted(self.judges.node_map), [2, 3])

        self.judges.on_judge_free(judge, 1)

        # The vanished submission is gone, and the judge moves on to the next queued one.
        self.assertNotIn(2, self.judges.node_map)
        self.assertNotIn(2, self.judges.submission_map)
        self.assertEqual(judge.submissions, [1, 3])
        self.assertEqual(self.judges.submission_map[3], judge)
        self.assertIn(judge, self.judges.judges)
