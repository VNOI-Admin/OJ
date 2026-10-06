import hashlib

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.templatetags.static import static
from django.utils.http import urlencode

from judge.models import Profile
from judge.utils.unicode import utf8bytes
from . import registry


@registry.function
def gravatar(email, size=80, default=None):
    # avoid external requests in official contest mode
    if settings.VNOJ_OFFICIAL_CONTEST_MODE:
        return static('icons/icon.svg')

    if isinstance(email, Profile):
        if default is None:
            default = email.mute
        email = email.user.email
    elif isinstance(email, AbstractUser):
        email = email.email

    gravatar_url = 'https://www.gravatar.com/avatar/' + hashlib.md5(utf8bytes(email.strip().lower())).hexdigest() + '?'
    args = {'d': 'identicon', 's': str(size)}
    if default:
        args['f'] = 'y'
    gravatar_url += urlencode(args)
    return gravatar_url
