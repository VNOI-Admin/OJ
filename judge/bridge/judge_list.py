import logging
from collections import namedtuple
from random import random
from threading import RLock

from django.conf import settings

from judge.bridge.judge_handler import SubmissionUnavailable
from judge.judge_priority import REJUDGE_PRIORITY
from judge.tasks import on_long_queue

try:
    from llist import dllist
except ImportError:
    from pyllist import dllist

logger = logging.getLogger('judge.bridge')

PriorityMarker = namedtuple('PriorityMarker', 'priority')

# Every judge carries a dispatch score, starting at zero. Failing to hand a submission over costs a
# point, succeeding gives one back, and dispatch always prefers the judges with the highest score.
# That way a judge failing for a transient reason is merely walked around instead of being dropped
# from the pool, which used to leave it connected but unusable until it happened to reconnect.
# A judge that runs out of score is disconnected, so it can come back with a clean slate.
MIN_JUDGE_SCORE = -3


class JudgeList(object):
    priorities = 4

    def __init__(self):
        self.queue = dllist()
        self.priority = [self.queue.append(PriorityMarker(i)) for i in range(self.priorities)]
        self.judges = set()
        self.node_map = {}
        self.submission_map = {}
        self.lock = RLock()
        self.min_tier = None
        self.problems = set()
        self.problem_ids = set()

    def _try_dispatch(self, judge, id, problem, language, source):
        with self.lock:
            try:
                judge.submit(id, problem, language, source)
            except SubmissionUnavailable:
                raise
            except Exception:
                logger.exception('Failed to dispatch %d (%s, %s) to %s', id, problem, language, judge.name)
                self._penalize_judge(judge)
                return False

            self.submission_map[id] = judge
            self._reward_judge(judge)
            return True

    def _reward_judge(self, judge):
        if judge.dispatch_score < 0:
            judge.dispatch_score += 1
            logger.info('Judge %s dispatched successfully, score is now %d', judge.name, judge.dispatch_score)

    def _penalize_judge(self, judge):
        with self.lock:
            judge.dispatch_score -= 1
            logger.warning('Lowered score of judge %s to %d', judge.name, judge.dispatch_score)
            if judge.dispatch_score > MIN_JUDGE_SCORE:
                return

            logger.error('Judge %s failed too many dispatches, disconnecting it', judge.name)
            self.remove(judge)
            try:
                judge.disconnect(force=True)
            except Exception:
                logger.exception('Failed to disconnect judge %s', judge.name)

    def _handle_free_judge(self, judge):
        with self.lock:
            if judge.tier > self.min_tier:
                return

            node = self.queue.first
            priority = 0
            while node:
                if isinstance(node.value, PriorityMarker):
                    priority = node.value.priority + 1
                elif priority >= REJUDGE_PRIORITY and self.should_reserve_judge():
                    return
                else:
                    id, problem, language, source, judge_id, banned_judges = node.value
                    if judge.name not in banned_judges and judge.can_judge(problem, language, judge_id):
                        try:
                            dispatched = self._try_dispatch(judge, id, problem, language, source)
                        except SubmissionUnavailable:
                            logger.error('Dropping queued submission %d, it is no longer available', id)
                            self.queue.remove(node)
                            del self.node_map[id]
                            return
                        if not dispatched:
                            # Leave the submission queued: the judge has been penalized, and whichever
                            # judge frees up next will pick this up instead.
                            return
                        logger.info('Dispatched queued submission %d: %s', id, judge.name)
                        self.queue.remove(node)
                        del self.node_map[id]
                        break
                node = node.next

    def _update_min_tier(self):
        with self.lock:
            old = self.min_tier
            try:
                self.min_tier = min(judge.tier for judge in self.judges
                                    if judge.tier is not None and not judge.is_disabled)
            except ValueError:
                self.min_tier = None

            if old != self.min_tier:
                logger.info('Minimum tier changed from %s to %s', old, self.min_tier)

            # We must be adding a judge, let register handle the new judge.
            if old is None:
                return

            # If the new min tier is larger, then we should treat all judges of the new tier as free and start grading.
            # This is only possible when removing a judge.
            if self.min_tier is not None and self.min_tier > old:
                for judge in self.current_tier_judges():
                    logger.info('Minimum tier increased, trying to dispatch to judge: %s', judge.name)
                    if not judge.working:
                        self._handle_free_judge(judge)

    def current_tier_judges(self):
        return [judge for judge in self.judges if judge.tier == self.min_tier and not judge.is_disabled]

    def should_reserve_judge(self):
        judges = self.current_tier_judges()
        if len(judges) <= 1:
            return False

        free_judges = sum(not judge.working for judge in judges)
        return free_judges <= 1

    def register(self, judge):
        with self.lock:
            # Disconnect all judges with the same name, see <https://github.com/DMOJ/online-judge/issues/828>
            self.disconnect(judge, force=True)
            self.judges.add(judge)
            self._update_min_tier()
            self._handle_free_judge(judge)

    def disconnect(self, judge_id, force=False):
        with self.lock:
            for judge in self.judges:
                if judge.name == judge_id:
                    judge.disconnect(force=force)

    def update_problems_all(
        self,
        new_problems,
        new_problem_ids,
        deleted_problems,
        deleted_problem_ids,
    ):
        with self.lock:
            self.problems = (self.problems | new_problems) - deleted_problems
            self.problem_ids = (
                self.problem_ids | new_problem_ids
            ) - deleted_problem_ids
            for judge in self.judges:
                judge.update_problems(
                    new_problems, new_problem_ids, deleted_problems, deleted_problem_ids,
                )
                if not judge.working:
                    self._handle_free_judge(judge)

    def update_problems(self, judge, problems, problem_ids):
        with self.lock:
            judge.replace_problems(problems, problem_ids)
            if not judge.working:
                self._handle_free_judge(judge)

    def update_disable_judge(self, judge_id, is_disabled):
        with self.lock:
            for judge in self.judges:
                if judge.name == judge_id:
                    judge.is_disabled = is_disabled
            self._update_min_tier()

    def remove(self, judge):
        with self.lock:
            sub = judge.get_current_submission()
            if sub is not None:
                try:
                    del self.submission_map[sub]
                except KeyError:
                    pass
            self.judges.discard(judge)
            self._update_min_tier()

            # Since we reserve a judge for high priority submissions when there are more than one,
            # we'll need to start judging if there is exactly one judge and it's free.
            current_tier = self.current_tier_judges()
            if len(current_tier) == 1:
                judge = next(iter(current_tier))
                if not judge.working:
                    self._handle_free_judge(judge)

    def __iter__(self):
        return iter(self.judges)

    def on_judge_free(self, judge, submission):
        logger.info('Judge available after grading %d: %s', submission, judge.name)
        with self.lock:
            # The submission may be missing if the judge picked it up despite the dispatch failing.
            self.submission_map.pop(submission, None)
            judge._working = False
            self._handle_free_judge(judge)

    def abort(self, submission):
        logger.info('Abort request: %d', submission)
        with self.lock:
            try:
                self.submission_map[submission].abort()
                return True
            except KeyError:
                try:
                    node = self.node_map[submission]
                except KeyError:
                    pass
                else:
                    self.queue.remove(node)
                    del self.node_map[submission]
                return False

    def check_priority(self, priority):
        return 0 <= priority < self.priorities

    def judge(self, id, problem, language, source, judge_id, priority, banned_judges=[]):
        with self.lock:
            if id in self.submission_map or id in self.node_map:
                # Already judging, don't queue again. This can happen during batch rejudges, rejudges should be
                # idempotent.
                return

            candidates = [
                judge for judge in self.current_tier_judges()
                if judge.name not in banned_judges and
                judge.can_judge(problem, language, judge_id)
            ]
            available = [judge for judge in candidates if not judge.working and not judge.is_disabled]
            if judge_id:
                logger.info('Specified judge %s is%savailable', judge_id, ' ' if available else ' not ')
            else:
                logger.info('Free judges: %d', len(available))

            if len(candidates) > 1 and len(available) == 1 and priority >= REJUDGE_PRIORITY:
                available = []

            # Schedule the submission on the healthiest judge reporting least load, walking to the
            # next one every time a dispatch fails, and queueing it if every judge refused it.
            while available:
                judge = min(available, key=lambda judge: (-judge.dispatch_score, judge.load, random()))
                available.remove(judge)

                if judge not in self.judges or judge.working:
                    continue

                try:
                    dispatched = self._try_dispatch(judge, id, problem, language, source)
                except SubmissionUnavailable:
                    logger.error('Dropping submission %d, it is no longer available', id)
                    return
                if dispatched:
                    logger.info('Dispatched submission %d to: %s', id, judge.name)
                    return

            self.node_map[id] = self.queue.insert(
                (id, problem, language, source, judge_id, banned_judges),
                self.priority[priority],
            )
            logger.info('Queued submission: %d', id)
            if self.queue.size == settings.VNOJ_LONG_QUEUE_ALERT_THRESHOLD + self.priorities:
                on_long_queue.delay()
