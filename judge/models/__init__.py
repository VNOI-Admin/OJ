from reversion import revisions

from judge.models.choices import ACE_THEMES, EFFECTIVE_MATH_ENGINES, MATH_ENGINES_CHOICES, TIMEZONE
from judge.models.comment import Comment, CommentLock, CommentVote
from judge.models.contest import Contest, ContestAnnouncement, ContestMoss, ContestParticipation, ContestProblem, \
    ContestSubmission, ContestTag, Rating
from judge.models.interface import BlogPost, BlogVote, MiscConfig, NavigationBar, validate_regex
from judge.models.problem import LanguageLimit, License, Problem, ProblemClarification, ProblemGroup, \
    ProblemTranslation, ProblemType, Solution, SubmissionSourceAccess, TranslatedProblemQuerySet
from judge.models.problem_data import CHECKERS, ProblemData, ProblemTestCase, problem_data_storage, \
    problem_directory_file
from judge.models.profile import Badge, Organization, OrganizationRequest, Profile, WebAuthnCredential
from judge.models.runtime import Judge, Language, RuntimeVersion
from judge.models.submission import SUBMISSION_RESULT, Submission, SubmissionSource, SubmissionTestCase
from judge.models.tag import Tag, TagData, TagGroup, TagProblem
from judge.models.ticket import GeneralIssue, Ticket, TicketMessage

revisions.register(Profile, exclude=['points', 'last_access', 'ip', 'rating'])
revisions.register(Problem, follow=['language_limits'])
revisions.register(LanguageLimit)
revisions.register(Contest, follow=['contest_problems'])
revisions.register(ContestProblem)
revisions.register(Organization)
revisions.register(BlogPost)
revisions.register(Solution)
revisions.register(Judge, fields=['name', 'created', 'auth_key', 'description'])
revisions.register(Language)
revisions.register(Comment, fields=['author', 'time', 'page', 'score', 'body', 'hidden', 'parent'])
revisions.register(TagProblem)
revisions.register(TagData, follow=['problem'])
del revisions
