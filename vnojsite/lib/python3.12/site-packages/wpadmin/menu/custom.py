from django.contrib import admin
from django.utils.text import capfirst
from django.urls import reverse

from wpadmin.menu.menus import Menu
from wpadmin.menu.items import MenuItem
from wpadmin.menu.utils import AppListElementMixin
from wpadmin.utils import get_admin_site, get_wpadmin_settings, get_admin_site_name

_site_cache = {}


def get_model_map(site):
    if site in _site_cache:
        return _site_cache[site]
    data = _site_cache[site] = {}
    for model in site._registry.keys():
        data['%s.%s' % (model._meta.app_label, model.__name__)] = model
    return data


class SubModelMenu(AppListElementMixin, MenuItem):
    def __init__(self, title, subtree, **kwargs):
        self.subtree = subtree
        super(SubModelMenu, self).__init__(title, **kwargs)

    def init_with_context(self, context):
        site = get_admin_site(context)

        visible_models = set()
        for app in site.get_app_list(context.get('request')):
            for model in app['models']:
                visible_models.add(f'{app["app_label"]}.{model["object_name"]}')

        model_map = {k: v for k, v in get_model_map(site).items() if k in visible_models}

        for entry in self.subtree:
            children = None
            kwargs = {}

            if isinstance(entry, dict):
                kwargs['title'] = entry.get('title')
                kwargs['icon'] = entry.get('icon')
                kwargs['url'] = entry.get('url')

                model = entry.get('model')
                children = entry.get('children')
            elif isinstance(entry, tuple) and len(entry) == 2:
                model, kwargs['icon'] = entry
            else:
                model = entry

            if model is not None:
                model = model_map.get(model)
                if model is None:
                    continue

                kwargs['url'] = self._get_admin_change_url(model, context)
                kwargs['add_url'] = self._get_admin_add_url(model, context)

                if kwargs.get('title') is None:
                    kwargs['title'] = capfirst(model._meta.verbose_name_plural)

            if isinstance(entry, dict):
                kwargs['description'] = entry.get('description', kwargs.get('title'))
            else:
                kwargs['description'] = kwargs.get('title')

            if children is None:
                self.children.append(MenuItem(**kwargs))
            else:
                self.children.append(SubModelMenu(subtree=children, **kwargs))

    def is_empty(self):
        return False


class CustomModelLeftMenu(Menu):
    def is_user_allowed(self, user):
        """
        Only users that are staff are allowed to see this menu.
        """
        return user.is_staff

    def get_model_children(self, context):
        if not self.is_user_allowed(context.get('request').user):
            return []

        tree = get_wpadmin_settings(get_admin_site_name(context)).get('custom_menu', [])
        menu = SubModelMenu('', tree)
        menu.init_with_context(context)
        return menu.children

    def init_with_context(self, context):
        self.children += self.get_model_children(context)


class CustomModelLeftMenuWithDashboard(CustomModelLeftMenu):
    def init_with_context(self, context):
        self.children.append(MenuItem(
            title='Dashboard',
            icon='fa-tachometer',
            url=reverse('%s:index' % get_admin_site_name(context)),
            description='Dashboard',
        ))
        super(CustomModelLeftMenuWithDashboard, self).init_with_context(context)
