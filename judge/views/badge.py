import os
from django import forms
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    FileResponse,
    Http404,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.urls import reverse
from django.utils.translation import gettext as _, gettext_lazy, ngettext
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from django.contrib import messages
from django.views.generic import DetailView, FormView, View

from judge.models import BadgeRequest, Badge
from judge.utils.views import TitleMixin


def validate_pdf(value):
    if not value.name.endswith(".pdf"):
        raise forms.ValidationError(_("Only PDF files are allowed."))


class BadgeRequestForm(forms.ModelForm):
    class Meta:
        model = BadgeRequest
        fields = ["badge", "desc", "cert", "new_badge_name"]

    def __init__(self, *args, **kwargs):
        super(BadgeRequestForm, self).__init__(*args, **kwargs)
        self.fields["badge"].queryset = Badge.objects.all()
        self.fields["badge"].required = False

    def clean(self):
        cleaned_data = super().clean()
        badge = cleaned_data.get("badge")
        new_badge_name = cleaned_data.get("new_badge_name")
        cert = cleaned_data.get("cert")

        if not badge and not new_badge_name:
            raise forms.ValidationError(
                "You must select an existing badge or enter a new badge name."
            )

        if badge:
            cleaned_data["badge"] = badge

        if cert:
            validate_pdf(cert)
        else:
            raise forms.ValidationError("The certificate field is required.")

        return cleaned_data


class RequestAddBadge(LoginRequiredMixin, FormView):
    template_name = "badge/request.html"
    form_class = BadgeRequestForm

    def dispatch(self, request, *args, **kwargs):
        return super(RequestAddBadge, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(RequestAddBadge, self).get_context_data(**kwargs)
        context["title"] = _("Request a new badge")
        return context

    def form_valid(self, form):
        badge_request = BadgeRequest()
        badge_request.user = self.request.user
        badge_request.badge = form.cleaned_data["badge"]
        badge_request.desc = form.cleaned_data["desc"]
        badge_request.cert = form.cleaned_data["cert"]
        badge_request.state = "P"
        badge_request.save()
        print("Form is valid. Redirecting...")
        return HttpResponseRedirect(
            reverse("request_badge_detail", args=(badge_request.id,))
        )

    def form_invalid(self, form):
        print("Form is invalid. Errors:", form.errors)
        return super().form_invalid(form)


class BadgeRequestDetail(LoginRequiredMixin, TitleMixin, DetailView):
    model = BadgeRequest
    template_name = "badge/detail.html"
    title = gettext_lazy("Badge request detail")
    pk_url_kwarg = "rpk"

    def get_object(self, queryset=None):
        object = super(BadgeRequestDetail, self).get_object(queryset)
        profile = self.request.profile
        if object.user_id != profile.id and not object.Badge.is_admin(profile):
            raise PermissionDenied()
        return object


BadgeRequestFormSet = forms.modelformset_factory(
    BadgeRequest, extra=0, fields=("state",), can_delete=True
)


class BadgeRequestBaseView(LoginRequiredMixin, View):
    model = Badge
    tab = None

    def get_object(self, queryset=None):
        badge = super(BadgeRequestBaseView, self).get_object(queryset)
        if not badge.is_admin(self.request.profile):
            raise PermissionDenied()
        return badge

    def get_requests(self):
        queryset = (
            self.object.requests.select_related("user__user")
            .defer(
                "user__about",
                "user__notes",
                "user__user_script",
            )
            .order_by("-id")
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super(BadgeRequestBaseView, self).get_context_data(**kwargs)
        context["title"] = _("Managing join requests for %s") % self.object.name
        context["content_title"] = format_html(
            _("Managing join requests for %s") % ' <a href="{1}">{0}</a>',
            self.object.name,
            self.object.get_absolute_url(),
        )
        context["tab"] = self.tab
        return context


class BadgeRequestView(BadgeRequestBaseView):
    template_name = "badge/pending.html"
    tab = "pending"

    def get_context_data(self, **kwargs):
        context = super(BadgeRequestView, self).get_context_data(**kwargs)
        context["formset"] = self.formset
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.formset = BadgeRequestFormSet(queryset=self.get_requests())
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_requests(self):
        return super().get_requests().filter(state="P")

    def post(self, request, *args, **kwargs):
        self.object = badge = self.get_object()
        self.formset = formset = BadgeRequestFormSet(
            request.POST, request.FILES, queryset=self.get_requests()
        )
        if formset.is_valid():
            approved, rejected = 0, 0
            for obj in formset.save():
                if obj.state == "A":
                    obj.user.badges.add(obj.badge)
                    approved += 1
                elif obj.state == "R":
                    rejected += 1
            messages.success(
                request,
                ngettext("Approved %d request.", "Approved %d requests.", approved)
                % approved
                + "\n"
                + ngettext("Rejected %d request.", "Rejected %d requests.", rejected)
                % rejected,
            )
            return HttpResponseRedirect(request.get_full_path())
        return self.render_to_response(self.get_context_data(object=badge))

    put = post


class BadgeRequestLog(BadgeRequestBaseView):
    states = ("A", "R")
    tab = "log"
    template_name = "badge/log.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super(BadgeRequestLog, self).get_context_data(**kwargs)
        context["requests"] = self.get_requests().filter(state__in=self.states)
        return context


def open_certificate(request, filename):
    # Check if the user is authenticated and an admin
    if not request.user.is_authenticated or not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to view this file.")

    # Path to the PDF file
    file_path = os.path.join(settings.MEDIA_ROOT, "certificates", filename)

    # Check if the file exists
    if os.path.exists(file_path):
        return FileResponse(open(file_path, "rb"), content_type="application/pdf")
    else:
        raise Http404("File does not exist")
