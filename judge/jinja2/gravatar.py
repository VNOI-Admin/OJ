from . import registry


@registry.function
def gravatar(email, size=80, default=None):
    return '/martor/logo/unk.png'
