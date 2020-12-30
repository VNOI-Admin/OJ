# clone from here: https://github.com/LQDJudge/online-judge/blob/master/judge/views/about.py
# thanks to LQD team
from django.shortcuts import render
from django.utils.translation import gettext as _


def about(request):
    return render(request, 'about/about.html', {
        'title': _('About'),
    })


def custom_checker_sample(request):
    return render(request, 'about/custom-checker-sample.html', {
        'title': _('Custom Checker Sample'),
    })