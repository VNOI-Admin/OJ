import os

from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.sitemaps.views import sitemap
from django.http import Http404, HttpResponsePermanentRedirect
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView
from martor.views import markdown_search_user

from judge.feed import AtomBlogFeed, AtomCommentFeed, AtomProblemFeed, BlogFeed, CommentFeed, ProblemFeed
from judge.sitemap import BlogPostSitemap, ContestSitemap, HomePageSitemap, OrganizationSitemap, ProblemSitemap, \
    SolutionSitemap, UrlSitemap, UserSitemap
from judge.views import TitledTemplateView, api, blog, comment, contests, language, license, mailgun, organization, \
    preview, problem, problem_manage, ranked_submission, register, stats, status, submission, tag, tasks, ticket, \
    two_factor, user, widgets
from judge.views.problem_data import ProblemDataView, ProblemSubmissionDiff, \
    problem_data_file, problem_init_view
from judge.views.register import ActivationView, RegistrationView
from judge.views.select2 import AssigneeSelect2View, CommentSelect2View, ContestSelect2View, \
    ContestUserSearchSelect2View, OrganizationSelect2View, OrganizationUserSelect2View, ProblemSelect2View, \
    TagGroupSelect2View, TagSelect2View, TicketUserSelect2View, UserSearchSelect2View, UserSelect2View
from judge.views.widgets import martor_image_uploader

admin.autodiscover()

SEND_ACTIVATION_EMAIL = getattr(settings, 'SEND_ACTIVATION_EMAIL', True)
REGISTRATION_COMPLETE_TEMPLATE = 'registration/registration_complete.html' if SEND_ACTIVATION_EMAIL \
                                 else 'registration/activation_complete.html'

register_patterns = [
    url(r'^activate/complete/$',
        TitledTemplateView.as_view(template_name='registration/activation_complete.html',
                                   title=_('Activation Successful!')),
        name='registration_activation_complete'),
    # Activation keys get matched by \w+ instead of the more specific
    # [a-fA-F0-9]{40} because a bad activation key should still get to the view;
    # that way it can return a sensible "invalid key" message instead of a
    # confusing 404.
    url(r'^activate/(?P<activation_key>\w+)/$',
        ActivationView.as_view(title=_('Activation key invalid')),
        name='registration_activate'),
    url(r'^register/$',
        RegistrationView.as_view(),
        name='registration_register'),
    url(r'^register/complete/$',
        TitledTemplateView.as_view(template_name=REGISTRATION_COMPLETE_TEMPLATE,
                                   title=_('Registration Completed')),
        name='registration_complete'),
    url(r'^register/closed/$',
        TitledTemplateView.as_view(template_name='registration/registration_closed.html',
                                   title=_('Registration not allowed')),
        name='registration_disallowed'),
    url(r'^login/$', user.CustomLoginView.as_view(), name='auth_login'),
    url(r'^logout/$', user.UserLogoutView.as_view(), name='auth_logout'),
    url(r'^password/change/$', user.CustomPasswordChangeView.as_view(), name='password_change'),
    url(r'^password/change/done/$', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html',
        title=_('Password change successful'),
    ), name='password_change_done'),
    url(r'^password/reset/$', user.CustomPasswordResetView.as_view(
        template_name='registration/password_reset.html',
        html_email_template_name='registration/password_reset_email.html',
        email_template_name='registration/password_reset_email.txt',
        title=_('Password reset'),
    ), name='password_reset'),
    url(r'^password/reset/confirm/(?P<uidb64>[0-9A-Za-z]+)-(?P<token>.+)/$',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            title=_('Enter new password'),
        ), name='password_reset_confirm'),
    url(r'^password/reset/complete/$', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
        title=_('Password reset complete'),
    ), name='password_reset_complete'),
    url(r'^password/reset/done/$', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
        title=_('Password reset sent'),
    ), name='password_reset_done'),
    url(r'^social/error/$', register.social_auth_error, name='social_auth_error'),

    url(r'^2fa/$', two_factor.TwoFactorLoginView.as_view(), name='login_2fa'),
    url(r'^2fa/enable/$', two_factor.TOTPEnableView.as_view(), name='enable_2fa'),
    url(r'^2fa/refresh/$', two_factor.TOTPRefreshView.as_view(), name='refresh_2fa'),
    url(r'^2fa/disable/$', two_factor.TOTPDisableView.as_view(), name='disable_2fa'),
    url(r'^2fa/webauthn/attest/$', two_factor.WebAuthnAttestationView.as_view(), name='webauthn_attest'),
    url(r'^2fa/webauthn/assert/$', two_factor.WebAuthnAttestView.as_view(), name='webauthn_assert'),
    url(r'^2fa/webauthn/delete/(?P<pk>\d+)$', two_factor.WebAuthnDeleteView.as_view(), name='webauthn_delete'),
    url(r'^2fa/scratchcode/generate/$', user.generate_scratch_codes, name='generate_scratch_codes'),

    url(r'api/token/generate/$', user.generate_api_token, name='generate_api_token'),
    url(r'api/token/remove/$', user.remove_api_token, name='remove_api_token'),
]


def exception(request):
    if not request.user.is_superuser:
        raise Http404()
    raise RuntimeError('@Xyene asked me to cause this')


def paged_list_view(view, name):
    return include([
        url(r'^$', view.as_view(), name=name),
        url(r'^(?P<page>\d+)$', view.as_view(), name=name),
    ])


urlpatterns = [
    url(r'^$', blog.PostList.as_view(template_name='home.html', title=_('Home')), kwargs={'page': 1}, name='home'),
    url(r'^500/$', exception),
    url(r'^admin/', admin.site.urls),
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^accounts/', include(register_patterns)),
    url(r'^', include('social_django.urls')),

    url(r'^problems', include([
        url(r'^/$', problem.ProblemList.as_view(), name='problem_list'),
        url(r'^/random/$', problem.RandomProblem.as_view(), name='problem_random'),
        url(r'^/suggest_list/$', problem.SuggestList.as_view(), name='problem_suggest_list'),
        url(r'^/suggest$', problem.ProblemSuggest.as_view(), name='problem_suggest'),
        url(r'^/create$', problem.ProblemCreate.as_view(), name='problem_create'),
    ])),

    url(r'^problem/(?P<problem>[^/]+)', include([
        url(r'^$', problem.ProblemDetail.as_view(), name='problem_detail'),
        url(r'^/edit$', problem.ProblemEdit.as_view(), name='problem_edit'),
        url(r'^/editorial$', problem.ProblemSolution.as_view(), name='problem_editorial'),
        url(r'^/raw$', problem.ProblemRaw.as_view(), name='problem_raw'),
        url(r'^/pdf$', problem.ProblemPdfView.as_view(), name='problem_pdf'),
        url(r'^/pdf/(?P<language>[a-z-]+)$', problem.ProblemPdfView.as_view(), name='problem_pdf'),
        url(r'^/clone', problem.ProblemClone.as_view(), name='problem_clone'),
        url(r'^/submit$', problem.ProblemSubmit.as_view(), name='problem_submit'),
        url(r'^/resubmit/(?P<submission>\d+)$', problem.ProblemSubmit.as_view(), name='problem_submit'),

        url(r'^/rank/', paged_list_view(ranked_submission.RankedSubmissions, 'ranked_submissions')),
        url(r'^/submissions/', paged_list_view(submission.ProblemSubmissions, 'chronological_submissions')),
        url(r'^/submissions/(?P<user>[\w-]+)/', paged_list_view(submission.UserProblemSubmissions, 'user_submissions')),

        url(r'^/$', lambda _, problem: HttpResponsePermanentRedirect(reverse('problem_detail', args=[problem]))),

        url(r'^/test_data$', ProblemDataView.as_view(), name='problem_data'),
        url(r'^/test_data/init$', problem_init_view, name='problem_data_init'),
        url(r'^/test_data/diff$', ProblemSubmissionDiff.as_view(), name='problem_submission_diff'),
        url(r'^/data/(?P<path>.+)$', problem_data_file, name='problem_data_file'),

        url(r'^/tickets$', ticket.ProblemTicketListView.as_view(), name='problem_ticket_list'),
        url(r'^/tickets/new$', ticket.NewProblemTicketView.as_view(), name='new_problem_ticket'),

        url(r'^/manage/submission', include([
            url('^$', problem_manage.ManageProblemSubmissionView.as_view(), name='problem_manage_submissions'),
            url('^/rejudge$', problem_manage.RejudgeSubmissionsView.as_view(), name='problem_submissions_rejudge'),
            url('^/rejudge/preview$', problem_manage.PreviewRejudgeSubmissionsView.as_view(),
                name='problem_submissions_rejudge_preview'),
            url('^/rejudge/success/(?P<task_id>[A-Za-z0-9-]*)$', problem_manage.rejudge_success,
                name='problem_submissions_rejudge_success'),
            url('^/rescore/all$', problem_manage.RescoreAllSubmissionsView.as_view(),
                name='problem_submissions_rescore_all'),
            url('^/rescore/success/(?P<task_id>[A-Za-z0-9-]*)$', problem_manage.rescore_success,
                name='problem_submissions_rescore_success'),
        ])),
    ])),

    url(r'^tags', include([
        url(r'^/$', tag.TagProblemList.as_view(), name='tagproblem_list'),
        url(r'^/create$', tag.TagProblemCreate.as_view(), name='tagproblem_create'),
        url(r'^/random/$', tag.TagRandomProblem.as_view(), name='tagproblem_random'),
        url(r'^/find/$', tag.TagFindProblem.as_view(), name='tagproblem_find'),
    ])),

    url(r'^tag/(?P<tagproblem>[^/]+)', include([
        url(r'^$', tag.TagProblemDetail.as_view(), name='tagproblem_detail'),
        url(r'^/assign$', tag.TagProblemAssign.as_view(), name='tagproblem_assign'),
        url(r'^/$', lambda _, problem: HttpResponsePermanentRedirect(reverse('tagproblem_detail', args=[tag]))),
    ])),

    url(r'^submissions/', paged_list_view(submission.AllSubmissions, 'all_submissions')),
    url(r'^submissions/diff$', submission.SubmissionSourceDiff, name='diff_submissions'),
    url(r'^submissions/user/(?P<user>[\w-]+)/', paged_list_view(submission.AllUserSubmissions, 'all_user_submissions')),

    url(r'^src/(?P<submission>\d+)$', submission.SubmissionSource.as_view(), name='submission_source'),
    url(r'^src/(?P<submission>\d+)/raw$', submission.SubmissionSourceRaw.as_view(), name='submission_source_raw'),

    url(r'^submission/(?P<submission>\d+)', include([
        url(r'^$', submission.SubmissionStatus.as_view(), name='submission_status'),
        url(r'^/abort$', submission.abort_submission, name='submission_abort'),
    ])),

    url(r'^users/', include([
        url(r'^$', user.users, name='user_list'),
        url(r'^(?P<page>\d+)$', lambda request, page:
            HttpResponsePermanentRedirect('%s?page=%s' % (reverse('user_list'), page))),
        url(r'^find$', user.user_ranking_redirect, name='user_ranking_redirect'),
    ])),

    url(r'^user$', user.UserAboutPage.as_view(), name='user_page'),
    url(r'^edit/profile/$', user.edit_profile, name='user_edit_profile'),
    url(r'^data/prepare/$', user.UserPrepareData.as_view(), name='user_prepare_data'),
    url(r'^data/download/$', user.UserDownloadData.as_view(), name='user_download_data'),
    url(r'^user/(?P<user>[\w-]+)', include([
        url(r'^$', user.UserAboutPage.as_view(), name='user_page'),
        url(r'^/ban$', user.UserBan.as_view(), name='user_ban'),
        url(r'^/blog/', paged_list_view(user.UserBlogPage, 'user_blog')),
        url(r'^/solved', include([
            url(r'^$', user.UserProblemsPage.as_view(), name='user_problems'),
            url(r'/ajax$', user.UserPerformancePointsAjax.as_view(), name='user_pp_ajax'),
        ])),
        url(r'^/submissions/', paged_list_view(submission.AllUserSubmissions, 'all_user_submissions_old')),
        url(r'^/submissions/', lambda _, user:
            HttpResponsePermanentRedirect(reverse('all_user_submissions', args=[user]))),

        url(r'^/$', lambda _, user: HttpResponsePermanentRedirect(reverse('user_page', args=[user]))),
    ])),

    url(r'^comments/upvote/$', comment.upvote_comment, name='comment_upvote'),
    url(r'^comments/downvote/$', comment.downvote_comment, name='comment_downvote'),
    url(r'^comments/hide/$', comment.comment_hide, name='comment_hide'),
    url(r'^comments/(?P<id>\d+)/', include([
        url(r'^edit$', comment.CommentEdit.as_view(), name='comment_edit'),
        url(r'^history/ajax$', comment.CommentRevisionAjax.as_view(), name='comment_revision_ajax'),
        url(r'^edit/ajax$', comment.CommentEditAjax.as_view(), name='comment_edit_ajax'),
        url(r'^votes/ajax$', comment.CommentVotesAjax.as_view(), name='comment_votes_ajax'),
        url(r'^render$', comment.CommentContent.as_view(), name='comment_content'),
    ])),

    url(r'^contests/', paged_list_view(contests.ContestList, 'contest_list')),
    path('contests.ics', contests.ContestICal.as_view(), name='contest_ical'),
    url(r'^contests/(?P<year>\d+)/(?P<month>\d+)/$', contests.ContestCalendar.as_view(), name='contest_calendar'),
    url(r'^contests/new/$', contests.CreateContest.as_view(), name='contest_new'),
    url(r'^contests/tag/(?P<name>[a-z-]+)', include([
        url(r'^$', contests.ContestTagDetail.as_view(), name='contest_tag'),
        url(r'^/ajax$', contests.ContestTagDetailAjax.as_view(), name='contest_tag_ajax'),
    ])),

    url(r'^contest/(?P<contest>\w+)', include([
        url(r'^$', contests.ContestDetail.as_view(), name='contest_view'),
        url(r'^/edit$', contests.EditContest.as_view(), name='contest_edit'),
        url(r'^/moss$', contests.ContestMossView.as_view(), name='contest_moss'),
        url(r'^/moss/delete$', contests.ContestMossDelete.as_view(), name='contest_moss_delete'),
        url(r'^/announce', contests.ContestAnnounce.as_view(), name='contest_announce'),
        url(r'^/clone$', contests.ContestClone.as_view(), name='contest_clone'),
        url(r'^/ranking/$', contests.ContestRanking.as_view(), name='contest_ranking'),
        url(r'^/official_ranking/$', contests.ContestOfficialRanking.as_view(), name='contest_official_ranking'),
        url(r'^/join$', contests.ContestJoin.as_view(), name='contest_join'),
        url(r'^/leave$', contests.ContestLeave.as_view(), name='contest_leave'),
        url(r'^/stats$', contests.ContestStats.as_view(), name='contest_stats'),
        url(r'^/data/prepare/$', contests.ContestPrepareData.as_view(), name='contest_prepare_data'),
        url(r'^/data/download/$', contests.ContestDownloadData.as_view(), name='contest_download_data'),

        url(r'^/rank/(?P<problem>\w+)/',
            paged_list_view(ranked_submission.ContestRankedSubmission, 'contest_ranked_submissions')),

        url(r'^/submissions/',
            paged_list_view(submission.AllContestSubmissions, 'contest_all_submissions')),
        url(r'^/submissions/(?P<user>[\w-]+)/',
            paged_list_view(submission.UserAllContestSubmissions, 'contest_all_user_submissions')),
        url(r'^/submissions/(?P<user>[\w-]+)/(?P<problem>\w+)/',
            paged_list_view(submission.UserContestSubmissions, 'contest_user_submissions')),

        url(r'^/participations$', contests.ContestParticipationList.as_view(), name='contest_participation_own'),
        url(r'^/participations/(?P<user>[\w-]+)$',
            contests.ContestParticipationList.as_view(), name='contest_participation'),
        url(r'^/participation/disqualify$', contests.ContestParticipationDisqualify.as_view(),
            name='contest_participation_disqualify'),

        url(r'^/$', lambda _, contest: HttpResponsePermanentRedirect(reverse('contest_view', args=[contest]))),
    ])),

    url(r'^contributors', include([
        url(r'^/$', user.ContribList.as_view(), name='contributors_list'),
        url(r'^/(?P<page>\d+)$', lambda request, page:
            HttpResponsePermanentRedirect('%s?page=%s' % (reverse('contributors_list'), page))),
        url(r'^/find$', user.user_contributor_redirect, name='user_contributor_redirect'),
    ])),

    url(r'^organizations/$', organization.OrganizationList.as_view(), name='organization_list'),
    url(r'^organizations/create/$', organization.CreateOrganization.as_view(), name='organization_create'),
    url(r'^organization/(?P<pk>\d+)-(?P<slug>[\w-]*)', include([
        url(r'^/', paged_list_view(organization.OrganizationHome, 'organization_home')),
        url(r'^/users$', organization.OrganizationUsers.as_view(), name='organization_users'),
        url(r'^/join$', organization.JoinOrganization.as_view(), name='join_organization'),
        url(r'^/leave$', organization.LeaveOrganization.as_view(), name='leave_organization'),
        url(r'^/edit$', organization.EditOrganization.as_view(), name='edit_organization'),
        url(r'^/kick$', organization.KickUserWidgetView.as_view(), name='organization_user_kick'),
        url(r'^/problems$', organization.ProblemListOrganization.as_view(), name='problem_list_organization'),
        url(r'^/contests$', organization.ContestListOrganization.as_view(), name='contest_list_organization'),
        url(r'^/submissions/',
            paged_list_view(organization.SubmissionListOrganization, 'submission_list_organization')),
        url(r'^/problem-create$', organization.ProblemCreateOrganization.as_view(), name='problem_create_organization'),
        url(r'^/contest-create$', organization.ContestCreateOrganization.as_view(), name='contest_create_organization'),

        url(r'^/request$', organization.RequestJoinOrganization.as_view(), name='request_organization'),
        url(r'^/request/(?P<rpk>\d+)$', organization.OrganizationRequestDetail.as_view(),
            name='request_organization_detail'),
        url(r'^/requests/', include([
            url(r'^pending$', organization.OrganizationRequestView.as_view(), name='organization_requests_pending'),
            url(r'^log$', organization.OrganizationRequestLog.as_view(), name='organization_requests_log'),
            url(r'^approved$', organization.OrganizationRequestLog.as_view(states=('A',), tab='approved'),
                name='organization_requests_approved'),
            url(r'^rejected$', organization.OrganizationRequestLog.as_view(states=('R',), tab='rejected'),
                name='organization_requests_rejected'),
        ])),

        url(r'^/post/', include([
            url('^new$', organization.BlogPostCreateOrganization.as_view(), name='blog_post_create_organization'),
        ])),

        url(r'^/$', lambda _, pk, slug: HttpResponsePermanentRedirect(reverse('organization_home', args=[pk, slug]))),
    ])),

    url(r'^runtimes/$', language.LanguageList.as_view(), name='runtime_list'),
    url(r'^runtimes/matrix/$', status.version_matrix, name='version_matrix'),
    url(r'^status/$', status.status_all, name='status_all'),
    url(r'^status/oj/$', status.status_oj, name='status_oj'),

    url(r'^api/', include([
        url(r'^contest/list$', api.api_v1_contest_list),
        url(r'^contest/info/(\w+)$', api.api_v1_contest_detail),
        url(r'^problem/list$', api.api_v1_problem_list),
        url(r'^problem/info/(\w+)$', api.api_v1_problem_info),
        url(r'^user/list$', api.api_v1_user_list),
        url(r'^user/info/([\w-]+)$', api.api_v1_user_info),
        url(r'^user/submissions/([\w-]+)$', api.api_v1_user_submissions),
        url(r'^user/ratings/(\d+)$', api.api_v1_user_ratings),
        url(r'^v2/', include([
            url(r'^contests$', api.api_v2.APIContestList.as_view()),
            url(r'^contest/(?P<contest>\w+)$', api.api_v2.APIContestDetail.as_view()),
            url(r'^problems$', api.api_v2.APIProblemList.as_view()),
            url(r'^problem/(?P<problem>\w+)$', api.api_v2.APIProblemDetail.as_view()),
            url(r'^users$', api.api_v2.APIUserList.as_view()),
            url(r'^user/(?P<user>[\w-]+)$', api.api_v2.APIUserDetail.as_view()),
            url(r'^submissions$', api.api_v2.APISubmissionList.as_view()),
            url(r'^submission/(?P<submission>\d+)$', api.api_v2.APISubmissionDetail.as_view()),
            url(r'^organizations$', api.api_v2.APIOrganizationList.as_view()),
            url(r'^participations$', api.api_v2.APIContestParticipationList.as_view()),
            url(r'^languages$', api.api_v2.APILanguageList.as_view()),
            url(r'^judges$', api.api_v2.APIJudgeList.as_view()),
        ])),
    ])),

    url(r'^post/', include([
        url(r'^', paged_list_view(blog.PostList, 'blog_post_list')),
        url(r'^(?P<id>\d+)-(?P<slug>.*)/', include([
            url(r'^$', blog.PostView.as_view(), name='blog_post'),
            url(r'^edit$', blog.BlogPostEdit.as_view(), name='blog_post_edit'),
        ])),
        url(r'^new$', blog.BlogPostCreate.as_view(), name='blog_post_new'),
    ])),

    url(r'^license/(?P<key>[-\w.]+)$', license.LicenseDetail.as_view(), name='license'),

    url(r'^mailgun/mail_activate/$', mailgun.MailgunActivationView.as_view(), name='mailgun_activate'),

    url(r'^widgets/', include([
        url(r'^rejudge$', widgets.rejudge_submission, name='submission_rejudge'),
        url(r'^single_submission$', submission.single_submission, name='submission_single_query'),
        url(r'^submission_testcases$', submission.SubmissionTestCaseQuery.as_view(), name='submission_testcases_query'),
        url(r'^detect_timezone$', widgets.DetectTimezone.as_view(), name='detect_timezone'),
        url(r'^status-table$', status.status_table, name='status_table'),

        url(r'^template$', problem.LanguageTemplateAjax.as_view(), name='language_template_ajax'),

        url(r'^select2/', include([
            url(r'^user_search$', UserSearchSelect2View.as_view(), name='user_search_select2_ajax'),
            url(r'^contest_users/(?P<contest>\w+)$', ContestUserSearchSelect2View.as_view(),
                name='contest_user_search_select2_ajax'),
            url(r'^ticket_user$', TicketUserSelect2View.as_view(), name='ticket_user_select2_ajax'),
            url(r'^ticket_assignee$', AssigneeSelect2View.as_view(), name='ticket_assignee_select2_ajax'),
        ])),

        url(r'^preview/', include([
            url(r'^default$', preview.DefaultMarkdownPreviewView.as_view(), name='default_preview'),
            url(r'^problem$', preview.ProblemMarkdownPreviewView.as_view(), name='problem_preview'),
            url(r'^blog$', preview.BlogMarkdownPreviewView.as_view(), name='blog_preview'),
            url(r'^contest$', preview.ContestMarkdownPreviewView.as_view(), name='contest_preview'),
            url(r'^comment$', preview.CommentMarkdownPreviewView.as_view(), name='comment_preview'),
            url(r'^flatpage$', preview.FlatPageMarkdownPreviewView.as_view(), name='flatpage_preview'),
            url(r'^profile$', preview.ProfileMarkdownPreviewView.as_view(), name='profile_preview'),
            url(r'^organization$', preview.OrganizationMarkdownPreviewView.as_view(), name='organization_preview'),
            url(r'^solution$', preview.SolutionMarkdownPreviewView.as_view(), name='solution_preview'),
            url(r'^license$', preview.LicenseMarkdownPreviewView.as_view(), name='license_preview'),
            url(r'^ticket$', preview.TicketMarkdownPreviewView.as_view(), name='ticket_preview'),
        ])),

        path('martor/', include([
            path('upload-image', martor_image_uploader, name='martor_image_uploader'),
            path('search-user', markdown_search_user, name='martor_search_user'),
        ])),
    ])),

    url(r'^feed/', include([
        url(r'^problems/rss/$', ProblemFeed(), name='problem_rss'),
        url(r'^problems/atom/$', AtomProblemFeed(), name='problem_atom'),
        url(r'^comment/rss/$', CommentFeed(), name='comment_rss'),
        url(r'^comment/atom/$', AtomCommentFeed(), name='comment_atom'),
        url(r'^blog/rss/$', BlogFeed(), name='blog_rss'),
        url(r'^blog/atom/$', AtomBlogFeed(), name='blog_atom'),
    ])),

    url(r'^stats/data/all/$', stats.all_data, name='stats_data_all'),

    url(r'^tickets/', include([
        url(r'^$', ticket.TicketList.as_view(), name='ticket_list'),
        url(r'^ajax$', ticket.TicketListDataAjax.as_view(), name='ticket_ajax'),
        url(r'^new$', ticket.NewIssueTicketView.as_view(), name='new_issue_ticket'),
    ])),

    url(r'^ticket/(?P<pk>\d+)', include([
        url(r'^$', ticket.TicketView.as_view(), name='ticket'),
        url(r'^/ajax$', ticket.TicketMessageDataAjax.as_view(), name='ticket_message_ajax'),
        url(r'^/open$', ticket.TicketStatusChangeView.as_view(open=True), name='ticket_open'),
        url(r'^/close$', ticket.TicketStatusChangeView.as_view(open=False), name='ticket_close'),
        url(r'^/good$', ticket.TicketStatusChangeView.as_view(contributive=True), name='ticket_good'),
        url(r'^/norm$', ticket.TicketStatusChangeView.as_view(contributive=False), name='ticket_norm'),
        url(r'^/notes$', ticket.TicketNotesEditView.as_view(), name='ticket_notes'),
    ])),

    url(r'^sitemap\.xml$', sitemap, {'sitemaps': {
        'problem': ProblemSitemap,
        'user': UserSitemap,
        'home': HomePageSitemap,
        'contest': ContestSitemap,
        'organization': OrganizationSitemap,
        'blog': BlogPostSitemap,
        'solutions': SolutionSitemap,
        'pages': UrlSitemap([
            {'location': '/about/', 'priority': 0.9},
        ]),
    }}),

    url(r'^judge-select2/', include([
        url(r'^profile/$', UserSelect2View.as_view(), name='profile_select2'),
        url(r'^organization_profile/(?P<pk>\d+)/$',
            OrganizationUserSelect2View.as_view(),
            name='organization_profile_select2'),
        url(r'^organization/$', OrganizationSelect2View.as_view(), name='organization_select2'),
        url(r'^problem/$', ProblemSelect2View.as_view(), name='problem_select2'),
        url(r'^contest/$', ContestSelect2View.as_view(), name='contest_select2'),
        url(r'^comment/$', CommentSelect2View.as_view(), name='comment_select2'),
        url(r'^tag/$', TagSelect2View.as_view(), name='tag_select2'),
        url(r'^taggroup/$', TagGroupSelect2View.as_view(), name='taggroup_select2'),
    ])),

    url(r'^tasks/', include([
        url(r'^status/(?P<task_id>[A-Za-z0-9-]*)$', tasks.task_status, name='task_status'),
        url(r'^ajax_status$', tasks.task_status_ajax, name='task_status_ajax'),
        url(r'^success$', tasks.demo_success),
        url(r'^failure$', tasks.demo_failure),
        url(r'^progress$', tasks.demo_progress),
    ])),
]

favicon_paths = ['apple-touch-icon-180x180.png', 'apple-touch-icon-114x114.png', 'android-chrome-72x72.png',
                 'apple-touch-icon-57x57.png', 'apple-touch-icon-72x72.png', 'apple-touch-icon.png', 'mstile-70x70.png',
                 'android-chrome-36x36.png', 'apple-touch-icon-precomposed.png', 'apple-touch-icon-76x76.png',
                 'apple-touch-icon-60x60.png', 'android-chrome-96x96.png', 'mstile-144x144.png', 'mstile-150x150.png',
                 'safari-pinned-tab.svg', 'android-chrome-144x144.png', 'apple-touch-icon-152x152.png',
                 'favicon-96x96.png',
                 'favicon-32x32.png', 'favicon-16x16.png', 'android-chrome-192x192.png', 'android-chrome-48x48.png',
                 'mstile-310x150.png', 'apple-touch-icon-144x144.png', 'browserconfig.xml', 'manifest.json',
                 'apple-touch-icon-120x120.png', 'mstile-310x310.png']

static_lazy = lazy(static, str)
for favicon in favicon_paths:
    urlpatterns.append(url(r'^%s$' % favicon, RedirectView.as_view(
        url=static_lazy('icons/' + favicon),
    )))

handler404 = 'judge.views.error.error404'
handler403 = 'judge.views.error.error403'
handler500 = 'judge.views.error.error500'

if 'newsletter' in settings.INSTALLED_APPS:
    urlpatterns.append(url(r'^newsletter/', include('newsletter.urls')))
if 'impersonate' in settings.INSTALLED_APPS:
    urlpatterns.append(url(r'^impersonate/', include('impersonate.urls')))

try:
    with open(os.path.join(os.path.dirname(__file__), 'local_urls.py')) as f:
        exec(f.read(), globals())
except IOError:
    pass
