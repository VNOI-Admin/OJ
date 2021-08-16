from celery import shared_task
from discord_webhook import DiscordEmbed, DiscordWebhook
from django.conf import settings
from django.contrib.contenttypes.models import ContentType


from judge.jinja2.gravatar import gravatar
from judge.models import Comment, Problem, Tag, TagProblem, Ticket

__all__ = ("on_new_ticket", "on_new_comment", "on_new_suggested_problem")


@shared_task
def on_new_ticket(ticket_id, content_type_id, object_id, message):
    webhook = settings.DISCORD_WEBHOOK.get('on_new_ticket', None)
    site_url = settings.SITE_FULL_URL
    if webhook is None or site_url is None:
        return
    ticket = Ticket.objects.get(pk=ticket_id)
    obj = ContentType.objects.get_for_id(content_type_id).get_object_for_this_type(
        pk=object_id,
    )
    url = obj.get_absolute_url()
    # for internal links, we add the site url
    if url[0] == '/':
        url = site_url + url
    webhook = DiscordWebhook(url=webhook)
    ticket_url = site_url + "/ticket/" + str(ticket_id)
    title = f"Title: [{ticket.title}]({ticket_url})"
    message = f"Message: {message}"
    embed = DiscordEmbed(
        title=f"New ticket on {url}",
        description=title + "\n" + message[:100],  # Should not too long
        color="03b2f8",
    )
    embed.set_author(
        name=ticket.user.user.username,
        url=site_url + "/user/" + ticket.user.user.username,
        icon_url=gravatar(ticket.user),
    )
    webhook.add_embed(embed)
    webhook.execute()


@shared_task
def on_new_comment(comment_id):
    webhook = settings.DISCORD_WEBHOOK.get('on_new_comment', None)
    site_url = settings.SITE_FULL_URL
    if webhook is None or site_url is None:
        return

    comment = Comment.objects.get(pk=comment_id)
    url = site_url + comment.get_absolute_url()

    webhook = DiscordWebhook(url=webhook)
    embed = DiscordEmbed(
        title=f"New comment {url}",
        description=comment.body[:200],  # should not too long
        color="03b2f8",
    )
    embed.set_author(
        name=comment.author.user.username,
        url=site_url + "/user/" + comment.author.user.username,
        icon_url=gravatar(comment.author),
    )
    webhook.add_embed(embed)
    webhook.execute()


@shared_task
def on_new_suggested_problem(problem_code):
    webhook = settings.DISCORD_WEBHOOK.get('on_new_suggested_problem', None)
    site_url = settings.SITE_FULL_URL
    if webhook is None or site_url is None:
        return

    problem = Problem.objects.get(code=problem_code)
    url = site_url + problem.get_absolute_url()
    description = f"Title: {problem.name}\n"
    description += f"Statement: {problem.description[:100]}..."

    webhook = DiscordWebhook(url=webhook)
    embed = DiscordEmbed(
        title=f"New suggested problem {url}",
        description=description,
        color="03b2f8",
    )
    embed.set_author(
        name=problem.suggester.user.username,
        url=site_url + "/user/" + problem.suggester.user.username,
        icon_url=gravatar(problem.suggester),
    )
    webhook.add_embed(embed)
    webhook.execute()


@shared_task
def on_new_tag_problem(problem_code):
    webhook = settings.DISCORD_WEBHOOK.get('on_new_tag_problem', None)
    site_url = settings.SITE_FULL_URL
    if webhook is None or site_url is None:
        return

    problem = TagProblem.objects.get(code=problem_code)
    url = site_url + problem.get_absolute_url()
    description = f'Title: {problem.name}\n'
    description += f'Judge: {problem.judge}'

    webhook = DiscordWebhook(url=webhook)
    embed = DiscordEmbed(
        title=f"New tag problem {url}",
        description=description,
        color="03b2f8",
    )

    webhook.add_embed(embed)
    webhook.execute()


@shared_task
def on_new_tag(problem_code, tag_list):
    webhook = settings.DISCORD_WEBHOOK.get('on_new_tag', None)
    site_url = settings.SITE_FULL_URL
    if webhook is None or site_url is None:
        return

    problem = TagProblem.objects.get(code=problem_code)

    tags = []
    for tag in tag_list:
        tags.append(Tag.objects.get(code=tag).name)

    url = site_url + problem.get_absolute_url()

    description = f'Title: {problem.name}\n'
    description += f'New tag: {", ".join(tags)}'

    webhook = DiscordWebhook(url=webhook)
    embed = DiscordEmbed(
        title=f"New tag added for problem {url}",
        description=description,
        color="03b2f8",
    )

    webhook.add_embed(embed)
    webhook.execute()
