import base64
import hmac
import json
import secrets
import struct

import pyotp
import webauthn
from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Max, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from fernet_fields import EncryptedCharField
from pyotp.utils import strings_equal
from sortedm2m.fields import SortedManyToManyField

from judge.models.choices import ACE_THEMES, MATH_ENGINES_CHOICES, SITE_THEMES, TIMEZONE
from judge.models.runtime import Language
from judge.ratings import rating_class
from judge.utils.float_compare import float_compare_equal
from judge.utils.two_factor import webauthn_decode

__all__ = ['Organization', 'OrganizationMonthlyUsage', 'Profile', 'OrganizationRequest', 'WebAuthnCredential']


class EncryptedNullCharField(EncryptedCharField):
    def get_prep_value(self, value):
        if not value:
            return None
        return super(EncryptedNullCharField, self).get_prep_value(value)


class Organization(models.Model):
    name = models.CharField(max_length=128, verbose_name=_('organization title'))
    slug = models.SlugField(max_length=128, verbose_name=_('organization slug'),
                            help_text=_('Organization name shown in URLs.'),
                            validators=[RegexValidator(r'^[a-zA-Z]',
                                                       _('Organization slugs must begin with a letter.'))],
                            unique=True)
    short_name = models.CharField(max_length=20, verbose_name=_('short name'),
                                  help_text=_('Displayed beside user name during contests.'))
    about = models.TextField(verbose_name=_('organization description'))
    admins = models.ManyToManyField('Profile', verbose_name=_('administrators'), related_name='admin_of',
                                    help_text=_('Those who can edit this organization.'))
    creation_date = models.DateTimeField(verbose_name=_('creation date'), auto_now_add=True)
    is_open = models.BooleanField(verbose_name=_('is open organization?'),
                                  help_text=_('Allow joining organization.'), default=False)
    is_unlisted = models.BooleanField(verbose_name=_('is unlisted organization?'),
                                      help_text=_('Organization will not be listed'), default=True)
    slots = models.IntegerField(verbose_name=_('maximum size'), null=True, blank=True,
                                help_text=_('Maximum amount of users in this organization, '
                                            'only applicable to private organizations.'))
    access_code = models.CharField(max_length=7, help_text=_('Student access code.'),
                                   verbose_name=_('access code'), null=True, blank=True)
    logo_override_image = models.CharField(verbose_name=_('logo override image'), default='', max_length=150,
                                           blank=True,
                                           help_text=_('This image will replace the default site logo for users '
                                                       'viewing the organization.'))
    performance_points = models.FloatField(default=0)
    member_count = models.IntegerField(default=0)
    current_consumed_credit = models.FloatField(default=0, help_text='Total used credit this month')
    available_credit = models.FloatField(default=0, help_text='Available credits')
    monthly_credit = models.FloatField(default=0, help_text='Total monthly free credit left')

    _pp_table = [pow(settings.VNOJ_ORG_PP_STEP, i) for i in range(settings.VNOJ_ORG_PP_ENTRIES)]

    def calculate_points(self, table=_pp_table):
        data = self.members.get_queryset().order_by('-performance_points') \
                   .values_list('performance_points', flat=True).filter(performance_points__gt=0)
        pp = settings.VNOJ_ORG_PP_SCALE * sum(ratio * pp for ratio, pp in zip(table, data))
        if not float_compare_equal(self.performance_points, pp):
            self.performance_points = pp
            self.save(update_fields=['performance_points'])
        return pp

    def on_user_changes(self):
        self.calculate_points()
        member_count = self.members.count()
        if self.member_count != member_count:
            self.member_count = member_count
            self.save(update_fields=['member_count'])

    @cached_property
    def admins_list(self):
        return self.admins.all()

    def is_admin(self, user):
        return user in self.admins_list

    def __contains__(self, item):
        if item is None:
            return False
        if isinstance(item, int):
            return self.members.filter(id=item).exists()
        elif isinstance(item, Profile):
            return self.members.filter(id=item.id).exists()
        else:
            raise TypeError('Organization membership test must be Profile or primary key.')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('organization_home', args=[self.slug])

    def get_users_url(self):
        return reverse('organization_users', args=[self.slug])

    def has_credit_left(self):
        return self.available_credit + self.monthly_credit > 0

    def consume_credit(self, consumed):
        # reduce credit in monthly credit first
        # then reduce the left to available credit
        if self.monthly_credit >= consumed:
            self.monthly_credit -= consumed
        else:
            consumed -= self.monthly_credit
            self.monthly_credit = 0
            # if available credit can be negative if we don't enable the monthly credit limitation
            self.available_credit -= consumed

        self.current_consumed_credit += consumed
        self.save(update_fields=['monthly_credit', 'available_credit', 'current_consumed_credit'])

    class Meta:
        ordering = ['name']
        permissions = (
            ('organization_admin', _('Administer organizations')),
            ('edit_all_organization', _('Edit all organizations')),
            ('change_open_organization', _('Change is_open field')),
            ('spam_organization', _('Create organization without limit')),
        )
        verbose_name = _('organization')
        verbose_name_plural = _('organizations')


class OrganizationMonthlyUsage(models.Model):
    organization = models.ForeignKey(Organization, verbose_name=_('organization'), related_name='monthly_usages',
                                     on_delete=models.CASCADE)
    time = models.DateField(verbose_name=_('time'))
    consumed_credit = models.FloatField(verbose_name=_('consumed credit'), default=0)

    class Meta:
        verbose_name = _('organization monthly usage')
        verbose_name_plural = _('organization monthly usages')
        unique_together = ('organization', 'time')


class Badge(models.Model):
    name = models.CharField(max_length=128, verbose_name=_('badge name'))
    mini = models.URLField(verbose_name=_('mini badge URL'), blank=True)
    full_size = models.URLField(verbose_name=_('full size badge URL'), blank=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    user = models.OneToOneField(User, verbose_name=_('user associated'), on_delete=models.CASCADE)
    about = models.TextField(verbose_name=_('self-description'), null=True, blank=True)
    timezone = models.CharField(max_length=50, verbose_name=_('time zone'), choices=TIMEZONE,
                                default=settings.DEFAULT_USER_TIME_ZONE)
    language = models.ForeignKey('Language', verbose_name=_('preferred language'), on_delete=models.SET_DEFAULT,
                                 default=Language.get_default_language_pk)
    points = models.FloatField(default=0)
    performance_points = models.FloatField(default=0)
    contribution_points = models.IntegerField(default=0)
    vnoj_points = models.IntegerField(default=0)
    problem_count = models.IntegerField(default=0)
    ace_theme = models.CharField(max_length=30, verbose_name=_('Ace theme'), choices=ACE_THEMES, default='auto')
    site_theme = models.CharField(max_length=10, verbose_name=_('site theme'), choices=SITE_THEMES, default='light')
    last_access = models.DateTimeField(verbose_name=_('last access time'), default=now)
    ip = models.GenericIPAddressField(verbose_name=_('last IP'), blank=True, null=True)
    ip_auth = models.GenericIPAddressField(verbose_name=_('IP-based authentication'),
                                           unique=True, blank=True, null=True)
    badges = models.ManyToManyField(Badge, verbose_name=_('badges'), blank=True, related_name='users')
    display_badge = models.ForeignKey(Badge, verbose_name=_('display badge'), null=True, on_delete=models.SET_NULL)
    organizations = SortedManyToManyField(Organization, verbose_name=_('organization'), blank=True,
                                          related_name='members', related_query_name='member')
    display_rank = models.CharField(max_length=10, default='user', verbose_name=_('display rank'),
                                    choices=settings.VNOJ_DISPLAY_RANKS)
    mute = models.BooleanField(verbose_name=_('comment mute'), help_text=_('Some users are at their best when silent.'),
                               default=False)
    is_unlisted = models.BooleanField(verbose_name=_('unlisted user'), help_text=_('User will not be ranked.'),
                                      default=False)
    ban_reason = models.TextField(null=True, blank=True,
                                  help_text=_('Show to banned user in login page.'))
    allow_tagging = models.BooleanField(verbose_name=_('Allow tagging'),
                                        help_text=_('User will be allowed to tag problems.'),
                                        default=True)
    rating = models.IntegerField(null=True, default=None)
    user_script = models.TextField(verbose_name=_('user script'), default='', blank=True, max_length=65536,
                                   help_text=_('User-defined JavaScript for site customization.'))
    current_contest = models.OneToOneField('ContestParticipation', verbose_name=_('current contest'),
                                           null=True, blank=True, related_name='+', on_delete=models.SET_NULL)
    math_engine = models.CharField(verbose_name=_('math engine'), choices=MATH_ENGINES_CHOICES, max_length=4,
                                   default=settings.MATHOID_DEFAULT_TYPE,
                                   help_text=_('The rendering engine used to render math.'))
    is_totp_enabled = models.BooleanField(verbose_name=_('TOTP 2FA enabled'), default=False,
                                          help_text=_('Check to enable TOTP-based two-factor authentication.'))
    is_webauthn_enabled = models.BooleanField(verbose_name=_('WebAuthn 2FA enabled'), default=False,
                                              help_text=_('Check to enable WebAuthn-based two-factor authentication.'))
    totp_key = EncryptedNullCharField(max_length=32, null=True, blank=True, verbose_name=_('TOTP key'),
                                      help_text=_('32-character Base32-encoded key for TOTP.'),
                                      validators=[RegexValidator('^$|^[A-Z2-7]{32}$',
                                                                 _('TOTP key must be empty or Base32.'))])
    scratch_codes = EncryptedNullCharField(max_length=255, null=True, blank=True, verbose_name=_('scratch codes'),
                                           help_text=_('JSON array of 16-character Base32-encoded codes '
                                                       'for scratch codes.'),
                                           validators=[
                                               RegexValidator(r'^(\[\])?$|^\[("[A-Z0-9]{16}", *)*"[A-Z0-9]{16}"\]$',
                                                              _('Scratch codes must be empty or a JSON array of '
                                                                '16-character Base32 codes.'))])
    last_totp_timecode = models.IntegerField(verbose_name=_('last TOTP timecode'), default=0)
    api_token = models.CharField(max_length=64, null=True, verbose_name=_('API token'),
                                 help_text=_('64-character hex-encoded API access token.'),
                                 validators=[RegexValidator('^[a-f0-9]{64}$',
                                                            _('API token must be None or hexadecimal'))])
    notes = models.TextField(verbose_name=_('internal notes'), null=True, blank=True,
                             help_text=_('Notes for administrators regarding this user.'))
    data_last_downloaded = models.DateTimeField(verbose_name=_('last data download time'), null=True, blank=True)
    username_display_override = models.CharField(max_length=100, blank=True, verbose_name=_('display name override'),
                                                 help_text=_('Name displayed in place of username.'))

    @cached_property
    def organization(self):
        # We do this to take advantage of prefetch_related
        # Don't need to filter here, because the prefetch_related has already filtered unlisted
        # orgs
        orgs = self.organizations.all()
        return orgs[0] if orgs else None

    @cached_property
    def username(self):
        return self.user.username

    @cached_property
    def display_name(self):
        return self.username_display_override or self.username

    @cached_property
    def has_enough_solves(self):
        return self.problem_count >= settings.VNOJ_INTERACT_MIN_PROBLEM_COUNT

    @cached_property
    def is_new_user(self):
        return not self.user.is_staff and not self.has_enough_solves

    @cached_property
    def is_banned(self):
        return not self.user.is_active and self.ban_reason is not None

    def can_be_banned_by(self, staff):
        return self.user != staff and not self.user.is_superuser and staff.has_perm('judge.ban_user')

    @cached_property
    def can_tag_problems(self):
        if self.allow_tagging:
            if self.user.has_perm('judge.add_tagproblem'):
                return True
            if self.rating is not None and self.rating >= settings.VNOJ_TAG_PROBLEM_MIN_RATING:
                return True
        return False

    @cached_property
    def resolved_ace_theme(self):
        if self.ace_theme != 'auto':
            return self.ace_theme
        if not self.user.has_perm('judge.test_site'):
            return settings.DMOJ_THEME_DEFAULT_ACE_THEME.get('light')
        if self.site_theme != 'auto':
            return settings.DMOJ_THEME_DEFAULT_ACE_THEME.get(self.site_theme)
        # This must be resolved client-side using prefers-color-scheme.
        return None

    @cached_property
    def registered_contest_ids(self):
        return set(self.contest_history.filter(virtual=0).values_list('contest_id', flat=True))

    _pp_table = [pow(settings.DMOJ_PP_STEP, i) for i in range(settings.DMOJ_PP_ENTRIES)]

    def calculate_points(self, table=_pp_table):
        from judge.models import Problem
        public_problems = Problem.get_public_problems()
        data = (
            public_problems.filter(submission__user=self, submission__points__isnull=False)
                           .annotate(max_points=Max('submission__points')).order_by('-max_points')
                           .values_list('max_points', flat=True).filter(max_points__gt=0)
        )
        bonus_function = settings.DMOJ_PP_BONUS_FUNCTION
        points = sum(data)
        problems = (
            public_problems.filter(submission__user=self, submission__result='AC',
                                   submission__case_points__gte=F('submission__case_total'))
            .values('id').distinct().count()
        )
        pp = sum(x * y for x, y in zip(table, data)) + bonus_function(problems)
        if not float_compare_equal(self.points, points) or \
           problems != self.problem_count or \
           not float_compare_equal(self.performance_points, pp):
            self.points = points
            self.problem_count = problems
            self.performance_points = pp
            self.save(update_fields=['points', 'problem_count', 'performance_points'])
            for org in self.organizations.get_queryset():
                org.calculate_points()
        return points

    calculate_points.alters_data = True

    def calculate_contribution_points(self):
        from judge.models import BlogPost, Comment, Ticket
        old_pp = self.contribution_points
        # Because the aggregate function can return None
        # So we use `X or 0` to get 0 if X is None
        # Please note that `0 or X` will return None if X is None
        total_comment_scores = Comment.objects.filter(author=self.id, hidden=False) \
            .aggregate(sum=Sum('score'))['sum'] or 0
        total_blog_scores = BlogPost.objects.filter(authors=self.id, visible=True, organization=None) \
            .aggregate(sum=Sum('score'))['sum'] or 0
        count_good_tickets = Ticket.objects.filter(user=self.id, is_contributive=True) \
            .count()
        count_suggested_problem = self.suggested_problems.filter(is_public=True).count()
        new_pp = (total_comment_scores + total_blog_scores) * settings.VNOJ_CP_COMMENT + \
            count_good_tickets * settings.VNOJ_CP_TICKET + \
            count_suggested_problem * settings.VNOJ_CP_PROBLEM
        if new_pp != old_pp:
            self.contribution_points = new_pp
            self.save(update_fields=['contribution_points'])
        return new_pp

    calculate_contribution_points.alters_data = True

    def update_contribution_points(self, delta):
        # this is just for testing the contribution
        # we should not use this function to update contribution points
        self.contribution_points += delta
        self.save(update_fields=['contribution_points'])
        return self.contribution_points

    update_contribution_points.alters_data = True

    def generate_api_token(self):
        secret = secrets.token_bytes(32)
        self.api_token = hmac.new(force_bytes(settings.SECRET_KEY), msg=secret, digestmod='sha256').hexdigest()
        self.save(update_fields=['api_token'])
        token = base64.urlsafe_b64encode(struct.pack('>I32s', self.user.id, secret))
        return token.decode('utf-8')

    generate_api_token.alters_data = True

    def generate_scratch_codes(self):
        def generate_scratch_code():
            return ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567') for _ in range(16))
        codes = [generate_scratch_code() for _ in range(settings.DMOJ_SCRATCH_CODES_COUNT)]
        self.scratch_codes = json.dumps(codes)
        self.save(update_fields=['scratch_codes'])
        return codes

    generate_scratch_codes.alters_data = True

    def remove_contest(self):
        self.current_contest = None
        self.save()

    remove_contest.alters_data = True

    def update_contest(self):
        contest = self.current_contest
        if contest is not None and (contest.ended or not contest.contest.is_accessible_by(self.user)):
            self.remove_contest()

    update_contest.alters_data = True

    def check_totp_code(self, code):
        totp = pyotp.TOTP(self.totp_key)
        now_timecode = totp.timecode(timezone.now())
        min_timecode = max(self.last_totp_timecode + 1, now_timecode - settings.DMOJ_TOTP_TOLERANCE_HALF_MINUTES)
        for timecode in range(min_timecode, now_timecode + settings.DMOJ_TOTP_TOLERANCE_HALF_MINUTES + 1):
            if strings_equal(code, totp.generate_otp(timecode)):
                self.last_totp_timecode = timecode
                self.save(update_fields=['last_totp_timecode'])
                return True
        return False

    check_totp_code.alters_data = True

    def ban_user(self, reason):
        self.ban_reason = reason
        self.display_rank = 'banned'
        self.is_unlisted = True
        self.save(update_fields=['ban_reason', 'display_rank', 'is_unlisted'])

        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

    ban_user.alters_data = True

    def unban_user(self):
        self.ban_reason = None
        self.display_rank = Profile._meta.get_field('display_rank').get_default()
        self.is_unlisted = False
        self.save(update_fields=['ban_reason', 'display_rank', 'is_unlisted'])

        self.user.is_active = True
        self.user.save(update_fields=['is_active'])

    unban_user.alters_data = True

    def get_absolute_url(self):
        return reverse('user_page', args=(self.user.username,))

    def __str__(self):
        return self.user.username

    @classmethod
    def get_user_css_class(cls, display_rank, rating, rating_colors=settings.DMOJ_RATING_COLORS):
        if rating_colors:
            return 'rating %s %s' % (rating_class(rating) if rating is not None else 'rate-none', display_rank)
        return display_rank

    @cached_property
    def css_class(self):
        return self.get_user_css_class(self.display_rank, self.rating)

    @cached_property
    def webauthn_id(self):
        return hmac.new(force_bytes(settings.SECRET_KEY), msg=b'webauthn:%d' % (self.id,), digestmod='sha256').digest()

    class Meta:
        permissions = (
            ('test_site', _('Shows in-progress development stuff')),
            ('totp', _('Edit TOTP settings')),
            ('can_upload_image', _('Can upload image directly to server via martor')),
            ('high_problem_timelimit', _('Can set high problem timelimit')),
            ('long_contest_duration', _('Can set long contest duration')),
            ('create_mass_testcases', _('Can create unlimitted number of testcases for a problem')),
            ('ban_user', _('Ban users')),
        )
        verbose_name = _('user profile')
        verbose_name_plural = _('user profiles')

        indexes = [
            models.Index(fields=('is_unlisted', '-performance_points')),
            models.Index(fields=('is_unlisted', '-contribution_points')),
            models.Index(fields=('is_unlisted', '-rating')),
            models.Index(fields=('is_unlisted', '-problem_count')),
        ]


class WebAuthnCredential(models.Model):
    user = models.ForeignKey(Profile, verbose_name=_('user'), related_name='webauthn_credentials',
                             on_delete=models.CASCADE)
    name = models.CharField(verbose_name=_('device name'), max_length=100)
    cred_id = models.CharField(verbose_name=_('credential ID'), max_length=255, unique=True)
    public_key = models.TextField(verbose_name=_('public key'))
    counter = models.BigIntegerField(verbose_name=_('sign counter'))

    @cached_property
    def webauthn_user(self):
        from judge.jinja2.gravatar import gravatar

        return webauthn.WebAuthnUser(
            user_id=self.user.webauthn_id,
            username=self.user.username,
            display_name=self.user.username,
            icon_url=gravatar(self.user.user.email),
            credential_id=webauthn_decode(self.cred_id),
            public_key=self.public_key,
            sign_count=self.counter,
            rp_id=settings.WEBAUTHN_RP_ID,
        )

    def __str__(self):
        return _('WebAuthn credential: %(name)s') % {'name': self.name}

    class Meta:
        verbose_name = _('WebAuthn credential')
        verbose_name_plural = _('WebAuthn credentials')


class OrganizationRequest(models.Model):
    user = models.ForeignKey(Profile, verbose_name=_('user'), related_name='requests', on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, verbose_name=_('organization'), related_name='requests',
                                     on_delete=models.CASCADE)
    time = models.DateTimeField(verbose_name=_('request time'), auto_now_add=True)
    state = models.CharField(max_length=1, verbose_name=_('state'), choices=(
        ('P', _('Pending')),
        ('A', _('Approved')),
        ('R', _('Rejected')),
    ))
    reason = models.TextField(verbose_name=_('reason'))

    class Meta:
        verbose_name = _('organization join request')
        verbose_name_plural = _('organization join requests')
