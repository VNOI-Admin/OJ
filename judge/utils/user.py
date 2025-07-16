import secrets

from django.conf import settings
from django.contrib.auth.models import User

from judge.models import Language, Profile


PASSWORD_ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'


def add_user(username, fullname, overwrite_existing=False):
    existing_user = User.objects.filter(username=username).first()
    if existing_user and not overwrite_existing:
        return ''

    if existing_user:
        usr = existing_user
    else:
        usr = User.objects.create_user(username=username, first_name=fullname, is_active=True)

    password = generate_password()
    usr.set_password(password)
    usr.save()

    if existing_user:
        profile = existing_user.profile
    else:
        profile = Profile.objects.create(user=usr)

    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
    profile.username_display_override = fullname
    profile.save()
    return password


def generate_password():
    return ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))
