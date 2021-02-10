from django.utils.translation import gettext as _
from django.utils.translation import ngettext

# You can put messages that you want to translate here
# Check this link for more information
# https://stackoverflow.com/questions/7878028/override-default-django-translations/20439571#20439571


# Translate Password validation
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

# NavBar
_("PRoblems")

# Footer
# _('proudly powered by <a href="https://dmoj.ca"><b>DMOJ</b></a>')
# _('proudly powered by <a href="https://dmoj.ca"><b>DMOJ</b></a>')
# _('follow us on <a href="https://github.com/VNOI-Admin/OJ"><b>Github</b></a> and <a href="https://www.facebook.com/vnoi.wiki"><b>Facebook</b></a>')