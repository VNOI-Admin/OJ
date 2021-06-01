from celery import shared_task
from discord_webhook import DiscordEmbed, DiscordWebhook
from django.conf import settings
from django.contrib.contenttypes.models import ContentType


from judge.jinja2.gravatar import gravatar
from judge.models import Ticket

__all__ = ("on_new_ticket", )


@shared_task
def on_new_ticket(ticket_id, content_type_id, object_id, message):
    webhook = settings.DISCORD_WEBHOOK
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
        description=title + "\n" + message,
        color="03b2f8",
    )
    embed.set_author(
        name=ticket.user.user.username,
        url=site_url + "/user/" + ticket.user.user.username,
        icon_url=gravatar(ticket.user),
    )
    webhook.add_embed(embed)
    webhook.execute()
