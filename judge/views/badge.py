from django import forms

from judge.models import BadgeRequest, Badge


class BadgeRequestForm(forms.ModelForm):
    new_badge_name = forms.CharField(required=False, label="New Badge Name")

    class Meta:
        model = BadgeRequest
        fields = ["badge", "desc", "cert"]

    def __init__(self, *args, **kwargs):
        super(BadgeRequestForm, self).__init__(*args, **kwargs)
        self.fields["badge"].queryset = Badge.objects.all()
        self.fields["badge"].required = False

    def clean(self):
        cleaned_data = super().clean()
        badge = cleaned_data.get("badge")
        new_badge_name = cleaned_data.get("new_badge_name")

        if not badge and not new_badge_name:
            raise forms.ValidationError(
                "You must select an existing badge or enter a new badge name."
            )

        return cleaned_data
