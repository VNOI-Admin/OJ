import hashlib
try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode
import urllib

from django import template

from wpadmin.utils import get_admin_site_name
from wpadmin.menu.utils import get_menu

register = template.Library()


class GravatarUrlNode(template.Node):
    def __init__(self, email, size='80', default=False, as_=None, variable=None):
        self.email = template.Variable(email)
        self.size = template.Variable(size)
        self.default = default
        self.variable = as_ and variable
 
    def render(self, context):
        try:
            email = self.email.resolve(context)
        except template.VariableDoesNotExist:
            return ''
        try:
            size = self.size.resolve(context)
        except template.VariableDoesNotExist:
            size = 80

        gravatar_url = '//www.gravatar.com/avatar/' + hashlib.md5(email.strip().lower().encode('utf-8')).hexdigest() + '?'
        args = {'d': 'identicon', 's': str(size)}
        if self.default:
            args['f'] = 'y'
        try:
            gravatar_url += urllib.urlencode(args)
        except AttributeError:
            gravatar_url += urllib.parse.urlencode(args)

        if self.variable is not None:
            context[self.variable] = gravatar_url
            return ''
        return gravatar_url


@register.tag
def gravatar_url(parser, token):
    try:
        return GravatarUrlNode(*token.split_contents()[1:])
    except ValueError:
        raise template.TemplateSyntaxError(
            '%r tag requires an email and an optional size' %
            token.contents.split()[0])


class IsMenuEnabledNode(template.Node):

    def __init__(self, menu_name):
        """
        menu_name - menu name ('top' or 'left')
        """
        self.menu_name = menu_name

    def render(self, context):
        menu = get_menu(self.menu_name, get_admin_site_name(context))
        if menu and menu.is_user_allowed(context.get('request').user):
            enabled = True
        else:
            enabled = False
        context['wpadmin_is_%s_menu_enabled' % self.menu_name] = enabled
        return ''


def wpadmin_is_left_menu_enabled(parser, token):
    return IsMenuEnabledNode('left')

register.tag('wpadmin_is_left_menu_enabled', wpadmin_is_left_menu_enabled)


def wpadmin_render_top_menu(context):
    menu = get_menu('top', get_admin_site_name(context))
    if not menu:
        from wpadmin.menu.menus import DefaultTopMenu
        menu = DefaultTopMenu()
    menu.init_with_context(context)
    context.update({
        'menu': menu,
        'is_user_allowed': menu.is_user_allowed(context.get('request').user),
    })
    return context

register.inclusion_tag(
    'wpadmin/menu/top_menu.html',
    takes_context=True)(wpadmin_render_top_menu)


def wpadmin_render_left_menu(context):
    menu = get_menu('left', get_admin_site_name(context))
    if menu:
        menu.init_with_context(context)
        context.update({
            'menu': menu,
            'is_user_allowed': menu.is_user_allowed(context.get('request').user),
        })
    return context

register.inclusion_tag(
    'wpadmin/menu/left_menu.html',
    takes_context=True)(wpadmin_render_left_menu)


def wpadmin_render_menu_top_item(context, item, is_first, is_last):
    item.init_with_context(context)
    if item.icon:
        icon = item.icon
    else:
        icon = 'fa-folder-o'
    context.update({
        'item': item,
        'is_first': is_first,
        'is_last': is_last,
        'icon': icon,
        'is_selected': item.is_selected(context.get('request')),
        'is_user_allowed': item.is_user_allowed(context.get('request').user),
    })
    return context

register.inclusion_tag(
    'wpadmin/menu/menu_top_item.html',
    takes_context=True)(wpadmin_render_menu_top_item)


def wpadmin_render_menu_item(context, item, is_first, is_last):
    item.init_with_context(context)
    context.update({
        'item': item,
        'is_first': is_first,
        'is_last': is_last,
        'is_selected': item.is_selected(context.get('request')),
        'is_user_allowed': item.is_user_allowed(context.get('request').user),
    })
    return context

register.inclusion_tag(
    'wpadmin/menu/menu_item.html',
    takes_context=True)(wpadmin_render_menu_item)


def wpadmin_render_user_tools(context, item, is_first, is_last):
    item.init_with_context(context)
    context.update({
        'item': item,
        'is_first': is_first,
        'is_last': is_last,
        'is_user_allowed': context.get('request').user.is_authenticated
        and item.is_user_allowed(context.get('request').user),
    })
    return context

register.inclusion_tag(
    'wpadmin/menu/user_tools.html',
    takes_context=True)(wpadmin_render_user_tools)
