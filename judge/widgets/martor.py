from martor.widgets import AdminMartorWidget as OldAdminMartorWidget, MartorWidget as OldMartorWidget

__all__ = ['MartorWidget', 'AdminMartorWidget']


class MartorWidget(OldMartorWidget):
    UPLOADS_ENABLED = True

    def build_attrs(self, base_attrs, extra_attrs=None):
        """Remove the 'required' attribute to prevent HTML5 validation errors.
        MartorWidget hides the actual textarea, which causes the browser to show
        'An invalid form control is not focusable' error when trying to validate
        a required field. Django's form validation will still work server-side.
        """
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs.pop('required', None)
        return attrs

    class Media:
        js = ['martor-mathjax.js']


class AdminMartorWidget(OldAdminMartorWidget):
    UPLOADS_ENABLED = True

    class Media:
        css = {
            'all': ['martor-description.css', 'featherlight.css'],
        }
        js = ['admin/js/jquery.init.js', 'martor-mathjax.js', 'libs/featherlight/featherlight.min.js']
