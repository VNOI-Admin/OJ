"""
Management command to add Blog navigation item to the navigation bar.
"""
from django.core.management.base import BaseCommand
from django.db import models

from judge.models import NavigationBar


class Command(BaseCommand):
    help = 'Add Blog navigation item to the navigation bar'

    def handle(self, *args, **options):
        if NavigationBar.objects.filter(key='blog').exists():
            self.stdout.write(self.style.WARNING('Blog navigation item already exists'))
            return

        max_order = NavigationBar.objects.aggregate(models.Max('order'))['order__max'] or 0

        blog_nav = NavigationBar.objects.create(
            key='blog',
            label='Blog',
            path='/blog/',
            regex=r'^/blog/',
            order=max_order + 10,
            parent=None,
        )

        self.stdout.write(self.style.SUCCESS(f'Successfully created Blog navigation item with order {blog_nav.order}'))
        self.stdout.write(self.style.SUCCESS('You can now access the blog at /blog/'))
