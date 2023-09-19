from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Count, FilteredRelation, Max, Q
from django.db.models.expressions import F, Value
from django.db.models.functions import Coalesce
from django.http import (Http404, HttpResponse, HttpResponseBadRequest,
                         HttpResponseForbidden, HttpResponseNotFound,
                         HttpResponseRedirect)
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import CreateView, ListView, UpdateView
from reversion import revisions

from judge.comments import CommentedDetailView
from judge.dblock import LockModel
from judge.forms import BlogPostForm
from judge.models import (BlogPost, BlogVote, Comment, Contest, Language,
                          Problem, Profile, Submission, Ticket)
from judge.tasks import on_new_blogpost
from judge.utils.cachedict import CacheDict
from judge.utils.diggpaginator import DiggPaginator
from judge.utils.opengraph import generate_opengraph
from judge.utils.tickets import filter_visible_tickets
from judge.utils.views import TitleMixin, generic_message


@login_required
def vote_blog(request, delta):
    if abs(delta) != 1:
        return HttpResponseBadRequest(_('Messing around, are we?'), content_type='text/plain')

    if request.method != 'POST':
        return HttpResponseForbidden()

    if 'id' not in request.POST or len(request.POST['id']) > 10:
        return HttpResponseBadRequest()

    if request.profile.is_new_user:
        return HttpResponseBadRequest(_('You must solve at least %d problems before you can vote.')
                                      % settings.VNOJ_INTERACT_MIN_PROBLEM_COUNT,
                                      content_type='text/plain')

    if request.profile.mute:
        suffix_msg = '' if request.profile.ban_reason is None else _(' Reason: ') + request.profile.ban_reason
        return HttpResponseBadRequest(_('Your part is silent, little toad.') + suffix_msg, content_type='text/plain')

    try:
        blog_id = int(request.POST['id'])
    except ValueError:
        return HttpResponseBadRequest()

    try:
        blog = BlogPost.objects.filter(id=blog_id).get()
    except BlogPost.DoesNotExist:
        return HttpResponseNotFound(_('Blog post not found.'), content_type='text/plain')

    if blog.authors.filter(id=request.profile.id).exists():
        return HttpResponseBadRequest(_('You cannot vote your own blog'), content_type='text/plain')

    vote = BlogVote()
    vote.blog_id = blog_id
    vote.voter = request.profile
    vote.score = delta

    while True:
        try:
            vote.save()
        except IntegrityError:
            with LockModel(write=(BlogVote,)):
                try:
                    vote = BlogVote.objects.get(blog_id=blog_id, voter=request.profile)
                except BlogVote.DoesNotExist:
                    # We must continue racing in case this is exploited to manipulate votes.
                    continue
                return HttpResponseBadRequest(_('You cannot vote twice.'), content_type='text/plain')
        else:
            BlogPost.objects.get(id=blog_id).vote(delta)
        break
    return HttpResponse('success', content_type='text/plain')


def upvote_blog(request):
    return vote_blog(request, 1)


def downvote_blog(request):
    return vote_blog(request, -1)


class BlogPostMixin(object):
    model = BlogPost
    pk_url_kwarg = 'id'
    slug_url_kwarg = 'slug'

    def get_object(self, queryset=None):
        post = super(BlogPostMixin, self).get_object(queryset)
        if not post.is_editable_by(self.request.user):
            raise PermissionDenied()
        return post


class PostListBase(ListView):
    model = BlogPost
    paginate_by = 10
    context_object_name = 'posts'
    title = None

    def get_paginator(self, queryset, per_page, orphans=0,
                      allow_empty_first_page=True, **kwargs):
        return DiggPaginator(queryset, per_page, body=6, padding=2,
                             orphans=orphans, allow_empty_first_page=allow_empty_first_page, **kwargs)

    def get_queryset(self):
        queryset = (BlogPost.objects.filter(visible=True, publish_on__lte=timezone.now())
                    .prefetch_related('authors__user', 'authors__display_badge'))
        if self.request.user.is_authenticated:
            profile = self.request.profile
            queryset = queryset.annotate(
                my_vote=FilteredRelation('votes', condition=Q(votes__voter_id=profile.id)),
            ).annotate(vote_score=Coalesce(F('my_vote__score'), Value(0)))
        return queryset

    def get_context_data(self, **kwargs):
        context = super(PostListBase, self).get_context_data(**kwargs)
        context['first_page_href'] = None
        context['title'] = self.title or _('Page %d of Posts') % context['page_obj'].number
        context['post_comment_counts'] = {
            int(page[2:]): count for page, count in
            Comment.objects
                   .filter(page__in=['b:%d' % post.id for post in context['posts']], hidden=False)
                   .values_list('page').annotate(count=Count('page')).order_by()
        }
        return context


class PostList(PostListBase):
    template_name = 'blog/list.html'
    show_all_blogs = False
    tab = 'home'

    def get_queryset(self):
        queryset = super(PostList, self).get_queryset()

        queryset = queryset.filter(organization=None)

        if 'show_all_blogs' in self.request.GET:
            self.show_all_blogs = self.request.session['show_all_blogs'] = self.request.GET['show_all_blogs'] == 'true'
        else:
            self.show_all_blogs = self.request.session.get('show_all_blogs', False)

        if self.show_all_blogs:
            self.tab = 'blog_list'
            queryset = queryset.order_by('-publish_on')
        else:
            queryset = queryset.filter(global_post=True).order_by('-sticky', '-publish_on')

        return queryset

    def get_context_data(self, **kwargs):
        context = super(PostList, self).get_context_data(**kwargs)
        context['first_page_href'] = reverse('home')

        context['newsfeed_link'] = f"{reverse('home')}?show_all_blogs=false"
        context['all_blogs_link'] = f"{reverse('home')}?show_all_blogs=true"

        context['show_all_blogs'] = self.show_all_blogs

        context['page_prefix'] = reverse('blog_post_list')
        context['comments'] = Comment.most_recent(self.request.user, 10)
        context['new_problems'] = Problem.get_public_problems() \
                                         .order_by('-date', 'code')[:settings.DMOJ_BLOG_NEW_PROBLEM_COUNT]
        context['page_titles'] = CacheDict(lambda page: Comment.get_page_title(page))

        context['user_count'] = Profile.objects.count
        context['problem_count'] = Problem.get_public_problems().count
        context['submission_count'] = lambda: Submission.objects.aggregate(max_id=Max('id'))['max_id'] or 0
        context['language_count'] = Language.objects.count

        now = timezone.now()

        visible_contests = Contest.get_visible_contests(self.request.user).filter(is_visible=True) \
                                  .order_by('start_time')

        context['current_contests'] = visible_contests.filter(start_time__lte=now, end_time__gt=now)
        context['future_contests'] = visible_contests.filter(start_time__gt=now)

        context['top_pp_users'] = self.get_top_pp_users()
        context['top_contrib'] = self.get_top_contributors()

        if self.request.user.is_authenticated:
            context['own_open_tickets'] = (
                Ticket.objects.filter(user=self.request.profile, is_open=True).order_by('-id')
                              .prefetch_related('linked_item').select_related('user__user', 'user__display_badge')
            )
        else:
            context['own_open_tickets'] = []

        # Superusers better be staffs, not the spell-casting kind either.
        if self.request.user.is_staff:
            tickets = (Ticket.objects.order_by('-id').filter(is_open=True).prefetch_related('linked_item')
                             .select_related('user__user', 'user__display_badge'))
            context['open_tickets'] = filter_visible_tickets(tickets, self.request.user)[:10]
        else:
            context['open_tickets'] = []

        context['tab'] = self.tab
        context['left_align_tabs'] = True

        return context

    def get_top_pp_users(self):
        return (Profile.objects.order_by('-performance_points')
                .filter(performance_points__gt=0, is_unlisted=False)
                .only('user', 'performance_points', 'display_rank', 'display_badge', 'rating',
                      'username_display_override')
                .select_related('user', 'display_badge')
                [:settings.VNOJ_HOMEPAGE_TOP_USERS_COUNT])

    def get_top_contributors(self):
        return (Profile.objects.order_by('-contribution_points')
                .filter(contribution_points__gt=0, is_unlisted=False)
                .only('user', 'contribution_points', 'display_rank', 'display_badge', 'rating',
                      'username_display_override')
                .select_related('user', 'display_badge')
                [:settings.VNOJ_HOMEPAGE_TOP_USERS_COUNT])


class PostView(TitleMixin, CommentedDetailView):
    model = BlogPost
    pk_url_kwarg = 'id'
    context_object_name = 'post'
    template_name = 'blog/content.html'

    def get_title(self):
        return self.object.title

    def get_comment_page(self):
        return 'b:%s' % self.object.id

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_authenticated:
            profile = self.request.profile
            queryset = queryset.annotate(
                my_vote=FilteredRelation('votes', condition=Q(votes__voter_id=profile.id)),
            ).annotate(vote_score=Coalesce(F('my_vote__score'), Value(0)))
        return queryset

    def get_context_data(self, **kwargs):
        context = super(PostView, self).get_context_data(**kwargs)

        metadata = generate_opengraph('generated-meta-blog:%d' % self.object.id,
                                      self.object.summary or self.object.content, 'blog')
        context['meta_description'] = metadata[0]
        context['og_image'] = self.object.og_image or metadata[1]

        return context

    def get_object(self, queryset=None):
        post = super(PostView, self).get_object(queryset)
        if not post.can_see(self.request.user):
            raise Http404()
        return post


class BlogPostCreate(TitleMixin, CreateView):
    template_name = 'blog/edit.html'
    model = BlogPost
    form_class = BlogPostForm

    def get_title(self):
        return _('Creating new blog post')

    def get_content_title(self):
        return _('Creating new blog post')

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            post = form.save()
            post.slug = self.request.user.username.lower()
            post.publish_on = timezone.now()
            post.authors.add(self.request.user.profile)
            post.save()

            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

        on_new_blogpost(post.id)

        return HttpResponseRedirect(post.get_absolute_url())

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        # hasattr(self, 'organization') -> admin org
        if request.official_contest_mode or request.user.profile.problem_count < settings.VNOJ_BLOG_MIN_PROBLEM_COUNT \
                and not request.user.is_superuser and not hasattr(self, 'organization'):
            return generic_message(request, _('Permission denied'),
                                   _('You cannot create blog post.\n'
                                     'Note: You need to solve at least %d problems to create new blog post.')
                                   % settings.VNOJ_BLOG_MIN_PROBLEM_COUNT)
        return super().dispatch(request, *args, **kwargs)


class BlogPostEdit(BlogPostMixin, TitleMixin, UpdateView):
    template_name = 'blog/edit.html'
    model = BlogPost
    form_class = BlogPostForm

    def get_title(self):
        return _('Updating blog post')

    def get_content_title(self):
        return _('Updating blog post')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['edit'] = True
        return context

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            revisions.set_comment(_('Edited from site'))
            revisions.set_user(self.request.user)
            return super(BlogPostEdit, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.official_contest_mode and not request.user.is_superuser:
            return generic_message(request, _('Permission denied'),
                                   _('You cannot edit blog post.'))
        return super().dispatch(request, *args, **kwargs)
