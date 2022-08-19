import pytz
from celery import shared_task
from discord_webhook import DiscordEmbed, DiscordWebhook
from django.conf import settings
from django.contrib.contenttypes.models import ContentType


from judge.jinja2.gravatar import gravatar
from judge.models import BlogPost, Comment, Contest, Problem, Tag, TagProblem, Ticket, TicketMessage

__all__ = ('on_new_ticket', 'on_new_comment', 'on_new_problem', 'on_new_tag_problem', 'on_new_tag', 'on_new_contest',
           'on_new_blogpost', 'on_new_ticket_message')


def get_webhook_url(event_name):
    default = settings.DISCORD_WEBHOOK.get('default', None)
    webhook = settings.DISCORD_WEBHOOK.get(event_name, default)
    return webhook


def send_webhook(webhook, title, description, author, color='03b2f8'):
    webhook = DiscordWebhook(url=webhook)

    embed = DiscordEmbed(
        title=title,
        description=description,
        color=color,
    )

    if author is not None:
        embed.set_author(
            name=author.user.username,
            url=settings.SITE_FULL_URL + '/user/' + author.user.username,
            icon_url=gravatar(author),
        )

    webhook.add_embed(embed)
    webhook.execute()


@shared_task
def on_new_ticket(ticket_id, content_type_id, object_id, message):
    webhook = get_webhook_url('on_new_ticket')
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    ticket = Ticket.objects.get(pk=ticket_id)
    obj = ContentType.objects.get_for_id(content_type_id).get_object_for_this_type(
        pk=object_id,
    )
    url = obj.get_absolute_url()
    # for internal links, we add the site url
    if url[0] == '/':
        url = settings.SITE_FULL_URL + url

    ticket_url = settings.SITE_FULL_URL + '/ticket/' + str(ticket_id)
    title = f'Title: [{ticket.title}]({ticket_url})'
    message = f'Message: {message}'
    send_webhook(webhook, f'New ticket on {url}', title + '\n' + message[:100], ticket.user)


@shared_task
def on_new_ticket_message(message_id, ticket_id, message):
    webhook = get_webhook_url('on_new_ticket_message')
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    ticket_message = TicketMessage.objects.get(pk=message_id)

    ticket_url = settings.SITE_FULL_URL + '/ticket/' + str(ticket_id)
    message = f'Message: {message}'

    send_webhook(webhook, f'New ticket reply on {ticket_url}', message[:100], ticket_message.user)


@shared_task
def on_new_comment(comment_id):
    webhook = get_webhook_url('on_new_comment')
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    comment = Comment.objects.get(pk=comment_id)
    url = settings.SITE_FULL_URL + comment.get_absolute_url()
    send_webhook(webhook, f'New comment {url}', comment.body[:200], comment.author)


@shared_task
def on_new_problem(problem_code, is_suggested=False):
    event_name = 'on_new_suggested_problem' if is_suggested else 'on_new_problem'
    webhook = get_webhook_url(event_name)
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    problem = Problem.objects.get(code=problem_code)
    author = problem.suggester or problem.authors.first()

    url = settings.SITE_FULL_URL + problem.get_absolute_url()
    title = f'New {"suggested" if is_suggested else "organization"} problem {url}'

    description = [
        ('Title', problem.name),
        ('Statement', problem.description[:100] + '...\n'),
        ('Time limit', problem.time_limit),
        ('Memory limit (MB)', problem.memory_limit / 1024),
        ('Points', problem.points),
    ]

    if problem.is_organization_private:
        orgs_link = [
            f'[{org.name}]({settings.SITE_FULL_URL + org.get_absolute_url()})'
            for org in problem.organizations.all()
        ]

        description.append(('Organizations', ' '.join(orgs_link)))

    description = '\n'.join(f'{opt}: {val}' for opt, val in description)

    send_webhook(webhook, title, description, author)


@shared_task
def on_new_tag_problem(problem_code):
    webhook = get_webhook_url('on_new_tag_problem')
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    problem = TagProblem.objects.get(code=problem_code)
    url = settings.SITE_FULL_URL + problem.get_absolute_url()
    description = f'Title: {problem.name}\n'
    description += f'Judge: {problem.judge}'

    send_webhook(webhook, f'New tag problem {url}', description, None)


@shared_task
def on_new_tag(problem_code, tag_list):
    webhook = get_webhook_url('on_new_tag')
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    problem = TagProblem.objects.get(code=problem_code)

    tags = []
    for tag in tag_list:
        tags.append(Tag.objects.get(code=tag).name)

    url = settings.SITE_FULL_URL + problem.get_absolute_url()

    description = f'Title: {problem.name}\n'
    description += f'New tag: {", ".join(tags)}'

    send_webhook(webhook, f'New tag added for problem {url}', description, None)


@shared_task
def on_new_contest(contest_key):
    webhook = get_webhook_url('on_new_contest')
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    contest = Contest.objects.get(key=contest_key)
    author = contest.authors.first()

    url = settings.SITE_FULL_URL + contest.get_absolute_url()
    title = f'New contest {url}'

    tz = pytz.timezone(settings.DEFAULT_USER_TIME_ZONE)

    description = [
        ('Title', contest.name),
        ('Statement', contest.description[:100] + '...\n'),
        ('Start time', contest.start_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')),
        ('End time', contest.end_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')),
        ('Duration', contest.end_time - contest.start_time),
    ]
    if contest.is_organization_private:
        orgs_link = [
            f'[{org.name}]({settings.SITE_FULL_URL + org.get_absolute_url()})'
            for org in contest.organizations.all()
        ]

        description.append(('Organizations', ' '.join(orgs_link)))

    description = '\n'.join(f'{opt}: {val}' for opt, val in description)

    send_webhook(webhook, title, description, author)


@shared_task
def on_new_blogpost(blog_id):
    webhook = get_webhook_url('on_new_blogpost')
    if webhook is None or settings.SITE_FULL_URL is None:
        return

    blog = BlogPost.objects.get(pk=blog_id)
    url = settings.SITE_FULL_URL + blog.get_absolute_url()

    description = f'Title: {blog.title}\n'
    description += f'Description: {blog.content[:200]}'
    send_webhook(webhook, f'New blog post {url}', description, blog.authors.first())
