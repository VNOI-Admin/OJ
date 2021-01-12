from django.utils.translation import gettext as _
from django.utils.translation import ngettext

# Put the default messages that you want to override here
ngettext(
    "This password is too short. It must contain at least %(min_length)d character.",
    "This password is too short. It must contain at least %(min_length)d characters.",
)
ngettext(
    "Your password must contain at least %(min_length)d character.",
    "Your password must contain at least %(min_length)d characters.",
)
_("The password is too similar to the %(verbose_name)s.")
_("Your password can't be too similar to your other personal information.")
_("This password is entirely numeric.")
_("Your password can't be entirely numeric.")
