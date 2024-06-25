"""
Django settings for dmoj project.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import datetime
import os

from django.utils.translation import gettext_lazy as _
from django_jinja.builtins import DEFAULT_EXTENSIONS
from jinja2 import select_autoescape

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '5*9f5q57mqmlz2#f$x1h76&jxy#yortjl1v+l*6hd18$d*yx#0'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

CSRF_FAILURE_VIEW = 'judge.views.widgets.csrf_failure'

SITE_ID = 1
SITE_NAME = 'DMOJ'
SITE_LONG_NAME = 'DMOJ: Modern Online Judge'
SITE_ADMIN_EMAIL = ''

DMOJ_REQUIRE_STAFF_2FA = True
# Display warnings that admins will not perform 2FA recovery.
DMOJ_2FA_HARDCORE = False

# Set to 1 to use HTTPS if request was made to https://
# Set to 2 to always use HTTPS for links
# Set to 0 to always use HTTP for links
DMOJ_SSL = 1

# Refer to dmoj.ca/post/103-point-system-rework
DMOJ_PP_STEP = 0.98514
DMOJ_PP_ENTRIES = 300
DMOJ_PP_BONUS_FUNCTION = lambda n: 0.05 * n  # 15 * (1 - 0.997 ** n)  # noqa: E731; 100 bai nua diem: 0.9930924

VNOJ_ORG_PP_STEP = 0.95
VNOJ_ORG_PP_ENTRIES = 100
VNOJ_ORG_PP_SCALE = 1

VNOJ_ENABLE_API = False

VNOJ_OFFICIAL_CONTEST_MODE = False

# Contribution points function
# Both should be int
VNOJ_CP_COMMENT = 1   # Each comment vote equals 1 CP
VNOJ_CP_TICKET = 10   # Each good ticket equals CP
VNOJ_CP_PROBLEM = 20  # Each suggested problem equal 20 CP

VNOJ_HOMEPAGE_TOP_USERS_COUNT = 5

VNOJ_DISPLAY_RANKS = (
    ('user', _('Normal User')),
    ('setter', _('Problem Setter')),
    ('daor', _('Bedao Team')),
    ('staff', _('Staff')),
    ('banned', _('Banned User')),
    ('admin', _('Admin')),
    ('teacher', _('Teacher')),
)

# Maximum number of organization a single user can be admin, to be able to
# create new organization, without the `spam_organization` permission
VNOJ_ORGANIZATION_ADMIN_LIMIT = 3
# Maximum timelimit (second) that a user can set for a problem
# without the `high_problem_timelimit` permission
VNOJ_PROBLEM_TIMELIMIT_LIMIT = 5
# Maximum contest duration (day) that a user can set for a contest
# without the `long_contest_duration` permission
VNOJ_CONTEST_DURATION_LIMIT = 14
# Maximum number of test cases that a user can create for a problem
# without the `create_mass_testcases` permission
VNOJ_TESTCASE_HARD_LIMIT = 100
# If a user without the `create_mass_testcases` permission create more than this amount of test
# they will receive a warning
VNOJ_TESTCASE_SOFT_LIMIT = 50
# Minimum problem count required to interact (comment, vote and update profile)
VNOJ_INTERACT_MIN_PROBLEM_COUNT = 5
# Minimum problem count required to create new blogs
VNOJ_BLOG_MIN_PROBLEM_COUNT = 10

VNOJ_TESTCASE_VISIBLE_LENGTH = 60

VNOJ_TAG_PROBLEM_MIN_RATING = 1900  # Minimum rating to be able to tag a problem

VNOJ_SHOULD_BAN_FOR_CHEATING_IN_CONTESTS = False
VNOJ_CONTEST_CHEATING_BAN_MESSAGE = 'Banned for multiple cheating offenses during contests'
VNOJ_MAX_DISQUALIFICATIONS_BEFORE_BANNING = 3

# List of subdomain that will be ignored in organization subdomain middleware
VNOJ_IGNORED_ORGANIZATION_SUBDOMAINS = ['oj', 'www', 'localhost']

# Some problems have a lot of testcases, and each testcase
# has about 5~6 fields, so we need to raise this
DATA_UPLOAD_MAX_NUMBER_FIELDS = 3000

# List of online judge preset for OJ API
OJ_PROBLEM_PRESET = [
    {
        'regex': r'^https://codeforces\.com/problemset/problem/(?P<contestid>\w+)/(?P<index>\w+)$',
        'codename': 'CF_%s_%s',
        'judge': 'Codeforces',
    },
    {
        'regex': r'^https://codeforces\.com/contest/(?P<contestid>\w+)/problem/(?P<index>\w+)$',
        'codename': 'CF_%s_%s',
        'judge': 'Codeforces',
    },
    {
        'regex': r'^^https://atcoder.jp/contests/(?:\w*)/tasks/(?P<codename>\w+)$',
        'codename': 'AC_%s',
        'judge': 'Atcoder',
    },
    {
        'regex': r'^https://oj\.vnoi\.info/problem/(?P<codename>\w+)$',
        'codename': 'VNOJ_%s',
        'judge': 'VNOJ',
    },
    {
        'regex': r'^https://open\.kattis\.com/problems/(?P<codename>\w+)$',
        'codename': 'KATTIS_%s',
        'judge': 'Kattis',
    },
    {
        'regex': r'^https://codeforces\.com/gym/(?P<contestid>\w+)/problem/(?P<index>\w+)$',
        'codename': 'CFGYM_%s_%s',
        'judge': 'CodeforcesGym',
    },
]

OJ_LIST = [
    ('Atcoder', 'Atcoder'),
    ('Codeforces', 'Codeforces'),
    ('CodeforcesGym', 'Codeforces (Gym)'),
    ('Kattis', 'Kattis'),
    ('VNOJ', 'VNOJ'),
]

OJ_REQUESTS_TIMEOUT = 5  # in seconds

OJAPI_CACHE_TIMEOUT = 3600  # Cache timeout for OJAPI data

# Urls of discord webhook.
# https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks
DISCORD_WEBHOOK = {
    'default': None,  # use this link if the specific link not found
    'on_new_ticket': None,
    'on_new_comment': None,
    'on_new_problem': None,
    'on_new_suggested_problem': None,
    'on_new_tag_problem': None,
    'on_new_tag': None,
    'on_new_blogpost': None,
    'on_error': None,
}

SITE_FULL_URL = None  # ie 'https://oj.vnoi.info', please remove the last / if needed

ACE_URL = '//cdnjs.cloudflare.com/ajax/libs/ace/1.1.3'
SELECT2_JS_URL = '//cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/js/select2.min.js'
SELECT2_CSS_URL = '//cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/css/select2.min.css'

DMOJ_CAMO_URL = None
DMOJ_CAMO_KEY = None
DMOJ_CAMO_HTTPS = False
DMOJ_CAMO_EXCLUDE = ()

DMOJ_PROBLEM_DATA_ROOT = None

DMOJ_PROBLEM_MIN_TIME_LIMIT = 0.01  # seconds
DMOJ_PROBLEM_MAX_TIME_LIMIT = 60  # seconds
DMOJ_PROBLEM_MIN_MEMORY_LIMIT = 0  # kilobytes
DMOJ_PROBLEM_MAX_MEMORY_LIMIT = 1048576  # kilobytes
DMOJ_PROBLEM_MIN_PROBLEM_POINTS = 0
DMOJ_PROBLEM_HOT_PROBLEM_COUNT = 7

DMOJ_PROBLEM_STATEMENT_DISALLOWED_CHARACTERS = {'“', '”', '‘', '’', '−', 'ﬀ', 'ﬁ', 'ﬂ', 'ﬃ', 'ﬄ'}
DMOJ_RATING_COLORS = True
DMOJ_EMAIL_THROTTLING = (10, 60)
VNOJ_DISCORD_WEBHOOK_THROTTLING = (10, 60)  # Max 10 messages in 60 seconds

# Maximum number of submissions a single user can queue without the `spam_submission` permission
DMOJ_SUBMISSION_LIMIT = 2
DMOJ_SUBMISSIONS_REJUDGE_LIMIT = 10

# Whether to allow users to view source code: 'all' | 'all-solved' | 'only-own'
DMOJ_SUBMISSION_SOURCE_VISIBILITY = 'all-solved'
DMOJ_BLOG_NEW_PROBLEM_COUNT = 7
DMOJ_TOTP_TOLERANCE_HALF_MINUTES = 1
DMOJ_SCRATCH_CODES_COUNT = 5
DMOJ_USER_MAX_ORGANIZATION_COUNT = 3

# Whether to allow users to download their data
DMOJ_USER_DATA_DOWNLOAD = False
DMOJ_USER_DATA_CACHE = ''
DMOJ_USER_DATA_INTERNAL = ''
DMOJ_USER_DATA_DOWNLOAD_RATELIMIT = datetime.timedelta(days=1)

# Whether to allow contest authors to download contest data
DMOJ_CONTEST_DATA_DOWNLOAD = False
DMOJ_CONTEST_DATA_CACHE = ''
DMOJ_CONTEST_DATA_INTERNAL = ''
DMOJ_CONTEST_DATA_DOWNLOAD_RATELIMIT = datetime.timedelta(days=1)

DMOJ_COMMENT_VOTE_HIDE_THRESHOLD = -5
DMOJ_COMMENT_REPLY_TIMEFRAME = datetime.timedelta(days=365)

DMOJ_PDF_PDFOID_URL = None
# Optional but recommended to save resources, path on disk to cache PDFs
DMOJ_PDF_PROBLEM_CACHE = None
# Optional, URL serving DMOJ_PDF_PROBLEM_CACHE with X-Accel-Redirect
DMOJ_PDF_PROBLEM_INTERNAL = None

DMOJ_STATS_LANGUAGE_THRESHOLD = 10
DMOJ_STATS_SUBMISSION_RESULT_COLORS = {
    'TLE': '#a3bcbd',
    'AC': '#00a92a',
    'WA': '#ed4420',
    'CE': '#42586d',
    'ERR': '#ffa71c',
}
DMOJ_API_PAGE_SIZE = 1000

DMOJ_PASSWORD_RESET_LIMIT_WINDOW = 3600
DMOJ_PASSWORD_RESET_LIMIT_COUNT = 10

# At the bare minimum, dark and light theme CSS file locations must be declared
DMOJ_THEME_CSS = {
    'light': 'style.css',
    'dark': 'dark/style.css',
}
# At the bare minimum, dark and light ace themes must be declared
DMOJ_THEME_DEFAULT_ACE_THEME = {
    'light': 'github',
    'dark': 'twilight',
}
DMOJ_SELECT2_THEME = 'dmoj'

MARKDOWN_STYLES = {}
MARKDOWN_DEFAULT_STYLE = {}

MATHOID_URL = False
MATHOID_GZIP = False
MATHOID_MML_CACHE = None
MATHOID_CSS_CACHE = 'default'
MATHOID_DEFAULT_TYPE = 'auto'
MATHOID_MML_CACHE_TTL = 86400
MATHOID_CACHE_ROOT = ''
MATHOID_CACHE_URL = False

TEXOID_GZIP = False
TEXOID_META_CACHE = 'default'
TEXOID_META_CACHE_TTL = 86400
DMOJ_NEWSLETTER_ID_ON_REGISTER = None

BAD_MAIL_PROVIDERS = ()
BAD_MAIL_PROVIDER_REGEX = ()
NOFOLLOW_EXCLUDED = set()

TIMEZONE_MAP = 'https://static.dmoj.ca/assets/earth.jpg'

TERMS_OF_SERVICE_URL = None
DEFAULT_USER_LANGUAGE = 'CPP17'

INLINE_JQUERY = True
INLINE_FONTAWESOME = True
JQUERY_JS = '//ajax.googleapis.com/ajax/libs/jquery/3.4.1/jquery.min.js'
FONTAWESOME_CSS = '//maxcdn.bootstrapcdn.com/font-awesome/4.3.0/css/font-awesome.min.css'
DMOJ_CANONICAL = 'oj.vnoi.info'

# Application definition

INSTALLED_APPS = ()

try:
    import wpadmin
except ImportError:
    pass
else:
    del wpadmin
    INSTALLED_APPS += ('wpadmin',)

    WPADMIN = {
        'admin': {
            'title': 'DMOJ Admin',
            'menu': {
                'top': 'wpadmin.menu.menus.BasicTopMenu',
                'left': 'wpadmin.menu.custom.CustomModelLeftMenuWithDashboard',
            },
            'custom_menu': [
                {
                    'model': 'judge.Problem',
                    'icon': 'fa-question-circle',
                    'children': [
                        'judge.ProblemGroup',
                        'judge.ProblemType',
                        'judge.License',
                    ],
                },
                {
                    'model': 'judge.TagProblem',
                    'icon': 'fa-tag',
                    'children': [
                        'judge.TagGroup',
                        'judge.Tag',
                    ],
                },
                ('judge.Submission', 'fa-check-square-o'),
                {
                    'model': 'judge.Language',
                    'icon': 'fa-file-code-o',
                    'children': [
                        'judge.Judge',
                    ],
                },
                {
                    'model': 'judge.Contest',
                    'icon': 'fa-bar-chart',
                    'children': [
                        'judge.ContestParticipation',
                        'judge.ContestTag',
                    ],
                },
                ('judge.Ticket', 'fa-bell'),
                {
                    'model': 'auth.User',
                    'icon': 'fa-user',
                    'children': [
                        'judge.Profile',
                        'judge.Badge',
                        'auth.Group',
                        'registration.RegistrationProfile',
                    ],
                },
                {
                    'model': 'judge.Organization',
                    'icon': 'fa-users',
                    'children': [
                        'judge.OrganizationRequest',
                    ],
                },
                {
                    'model': 'judge.NavigationBar',
                    'icon': 'fa-bars',
                    'children': [
                        'sites.Site',
                        'redirects.Redirect',
                    ],
                },
                ('judge.BlogPost', 'fa-rss-square'),
                {
                    'model': 'judge.Comment',
                    'icon': 'fa-comment-o',
                    'children': [
                        'judge.CommentLock',
                    ],
                },
                ('flatpages.FlatPage', 'fa-file-text-o'),
                ('judge.MiscConfig', 'fa-question-circle'),
            ],
            'dashboard': {
                'breadcrumbs': True,
            },
        },
    }

INSTALLED_APPS += (
    'django.contrib.admin',
    'judge',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.flatpages',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.redirects',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'registration',
    'mptt',
    'reversion',
    'django_social_share',
    'social_django',
    'compressor',
    'django_ace',
    'sortedm2m',
    'statici18n',
    'impersonate',
    'django_jinja',
    'martor',
    'adminsortable2',
    'django_cleanup.apps.CleanupConfig',
)

MIDDLEWARE = (
    'judge.middleware.ShortCircuitMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'judge.middleware.APIMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'judge.middleware.MiscConfigMiddleware',
    'judge.middleware.DMOJLoginMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'judge.user_log.LogUserAccessMiddleware',
    'judge.timezone.TimezoneMiddleware',
    'impersonate.middleware.ImpersonateMiddleware',
    'judge.middleware.DMOJImpersonationMiddleware',
    'judge.middleware.ContestMiddleware',
    'django.contrib.flatpages.middleware.FlatpageFallbackMiddleware',
    'judge.social_auth.SocialAuthExceptionMiddleware',
    'django.contrib.redirects.middleware.RedirectFallbackMiddleware',
)

IMPERSONATE_REQUIRE_SUPERUSER = True
IMPERSONATE_DISABLE_LOGGING = True

ACCOUNT_ACTIVATION_DAYS = 7

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'judge.utils.pwned.PwnedPasswordsValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

SILENCED_SYSTEM_CHECKS = ['urls.W002', 'fields.W342']

ROOT_URLCONF = 'dmoj.urls'
LOGIN_REDIRECT_URL = '/user'
WSGI_APPLICATION = 'dmoj.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

TEMPLATES = [
    {
        'BACKEND': 'django_jinja.backend.Jinja2',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'APP_DIRS': False,
        'OPTIONS': {
            'match_extension': ('.html', '.txt'),
            'match_regex': '^(?!admin/)',
            'context_processors': [
                'django.template.context_processors.media',
                'django.template.context_processors.tz',
                'django.template.context_processors.i18n',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
                'judge.template_context.comet_location',
                'judge.template_context.get_resource',
                'judge.template_context.general_info',
                'judge.template_context.site',
                'judge.template_context.site_name',
                'judge.template_context.site_theme',
                'judge.template_context.misc_config',
                'judge.template_context.math_setting',
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
            ],
            'autoescape': select_autoescape(['html', 'xml']),
            'trim_blocks': True,
            'lstrip_blocks': True,
            'translation_engine': 'judge.utils.safe_translations',
            'extensions': DEFAULT_EXTENSIONS + [
                'compressor.contrib.jinja2ext.CompressorExtension',
                'judge.jinja2.DMOJExtension',
                'judge.jinja2.spaceless.SpacelessExtension',
            ],
            'bytecode_cache': {
                'enabled': True,
            },
        },
    },
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.media',
                'django.template.context_processors.tz',
                'django.template.context_processors.i18n',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

LANGUAGES = [
    ('en', _('English')),
    ('vi', _('Vietnamese')),
]

BLEACH_USER_SAFE_TAGS = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'b', 'i', 'strong', 'em', 'tt', 'del', 'kbd', 's', 'abbr', 'cite', 'mark', 'q', 'samp', 'small',
    'u', 'var', 'wbr', 'dfn', 'ruby', 'rb', 'rp', 'rt', 'rtc', 'sub', 'sup', 'time', 'data',
    'p', 'br', 'pre', 'span', 'div', 'blockquote', 'code', 'hr',
    'ul', 'ol', 'li', 'dd', 'dl', 'dt', 'address', 'section', 'details', 'summary',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col', 'tfoot',
    'img', 'audio', 'video', 'source',
    'a', 'strike',
    'style', 'noscript', 'center', 'object', 'iframe',
]

BLEACH_USER_SAFE_ATTRS = {
    '*': ['id', 'class', 'style', 'data', 'height'],
    'img': ['src', 'alt', 'title', 'width', 'height', 'data-src', 'align'],
    'a': ['href', 'alt', 'title'],
    'iframe': ['src', 'height', 'width', 'allow'],
    'abbr': ['title'],
    'dfn': ['title'],
    'time': ['datetime'],
    'data': ['value'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
    'audio': ['autoplay', 'controls', 'crossorigin', 'muted', 'loop', 'preload', 'src'],
    'video': ['autoplay', 'controls', 'crossorigin', 'height', 'muted', 'loop', 'poster', 'preload', 'src', 'width'],
    'source': ['src', 'srcset', 'type'],
    'li': ['value'],
}

MARKDOWN_STAFF_EDITABLE_STYLE = {
    'safe_mode': False,
    'use_camo': True,
    'texoid': True,
    'math': True,
    'bleach': {
        'tags': BLEACH_USER_SAFE_TAGS,
        'attributes': BLEACH_USER_SAFE_ATTRS,
        'styles': True,
        'mathml': True,
    },
}

MARKDOWN_ADMIN_EDITABLE_STYLE = {
    'safe_mode': False,
    'use_camo': True,
    'texoid': True,
    'math': True,
}

MARKDOWN_DEFAULT_STYLE = {
    'safe_mode': True,
    'nofollow': True,
    'use_camo': True,
    'math': True,
}

MARKDOWN_USER_LARGE_STYLE = {
    'safe_mode': True,
    'nofollow': True,
    'use_camo': True,
    'math': True,
}

MARKDOWN_STYLES = {
    'default': MARKDOWN_DEFAULT_STYLE,
    'comment': MARKDOWN_DEFAULT_STYLE,
    'self-description': MARKDOWN_USER_LARGE_STYLE,
    'problem': MARKDOWN_STAFF_EDITABLE_STYLE,
    'problem-full': MARKDOWN_ADMIN_EDITABLE_STYLE,
    'contest': MARKDOWN_STAFF_EDITABLE_STYLE,
    'flatpage': MARKDOWN_ADMIN_EDITABLE_STYLE,
    'language': MARKDOWN_STAFF_EDITABLE_STYLE,
    'license': MARKDOWN_STAFF_EDITABLE_STYLE,
    'judge': MARKDOWN_STAFF_EDITABLE_STYLE,
    'blog': MARKDOWN_STAFF_EDITABLE_STYLE,
    'solution': MARKDOWN_STAFF_EDITABLE_STYLE,
    'contest_tag': MARKDOWN_STAFF_EDITABLE_STYLE,
    'organization-about': MARKDOWN_USER_LARGE_STYLE,
    'ticket': MARKDOWN_USER_LARGE_STYLE,
}

MARTOR_ENABLE_CONFIGS = {
    'imgur': 'true',
    'mention': 'true',
    'jquery': 'false',
    'living': 'false',
    'spellcheck': 'false',
    'hljs': 'false',
}
MARTOR_MARKDOWNIFY_URL = '/widgets/preview/default'
MARTOR_SEARCH_USERS_URL = '/widgets/martor/search-user'
MARTOR_UPLOAD_URL = '/widgets/martor/upload-image'
MARTOR_MARKDOWN_BASE_MENTION_URL = '/user/'
MARTOR_UPLOAD_URL_PREFIX = '/martor'

# Directory under MEDIA_ROOT to use to store image uploaded through martor.
MARTOR_UPLOAD_MEDIA_DIR = 'martor'
MARTOR_UPLOAD_SAFE_EXTS = {'.jpg', '.png', '.gif', '.svg'}

PDF_STATEMENT_UPLOAD_URL_PREFIX = '/pdf'
PDF_STATEMENT_UPLOAD_MEDIA_DIR = 'pdf'
PDF_STATEMENT_SAFE_EXTS = {'pdf'}
PDF_STATEMENT_MAX_FILE_SIZE = 5242880

SUBMISSION_FILE_UPLOAD_URL_PREFIX = '/submission_file'
SUBMISSION_FILE_UPLOAD_MEDIA_DIR = 'submission_file'

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    },
}

ENABLE_FTS = False

# Bridged configuration
BRIDGED_JUDGE_ADDRESS = [('localhost', 9999)]
BRIDGED_JUDGE_PROXIES = None
BRIDGED_DJANGO_ADDRESS = [('localhost', 9998)]
BRIDGED_DJANGO_CONNECT = None

# Event Server configuration
EVENT_DAEMON_USE = False
EVENT_DAEMON_POST = 'ws://localhost:9997/'
EVENT_DAEMON_GET = 'ws://localhost:9996/'
EVENT_DAEMON_POLL = '/channels/'
EVENT_DAEMON_KEY = None
EVENT_DAEMON_AMQP_EXCHANGE = 'dmoj-events'
EVENT_DAEMON_SUBMISSION_KEY = '6Sdmkx^%pk@GsifDfXcwX*Y7LRF%RGT8vmFpSxFBT$fwS7trc8raWfN#CSfQuKApx&$B#Gh2L7p%W!Ww'
EVENT_DAEMON_CONTEST_KEY = '&w7hB-.9WnY2Jj^Qm+|?o6a<!}_2Wiw+?(_Yccqq{uR;:kWQP+3R<r(ICc|4^dDeEuJE{*D;Gg@K(4K>'

# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

# Whatever you do, this better be one of the entries in `LANGUAGES`.
LANGUAGE_CODE = 'en'
TIME_ZONE = 'UTC'
DEFAULT_USER_TIME_ZONE = 'America/Toronto'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Cookies
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

DMOJ_RESOURCES = os.path.join(BASE_DIR, 'resources')
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
)
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'resources'),
]
STATIC_URL = '/static/'

# Define a cache
CACHES = {}

# Authentication
AUTHENTICATION_BACKENDS = (
    'social_core.backends.google.GoogleOAuth2',
    'social_core.backends.facebook.FacebookOAuth2',
    'judge.social_auth.GitHubSecureEmailOAuth2',
    'django.contrib.auth.backends.ModelBackend',
)

SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'judge.social_auth.verify_email',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.social_auth.associate_by_email',
    'judge.social_auth.get_username_password',
    'social_core.pipeline.user.create_user',
    'judge.social_auth.add_password',
    'judge.social_auth.make_profile',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
)

SOCIAL_AUTH_GITHUB_SECURE_SCOPE = ['user:email']
SOCIAL_AUTH_FACEBOOK_SCOPE = ['email']
SOCIAL_AUTH_SLUGIFY_USERNAMES = True
SOCIAL_AUTH_SLUGIFY_FUNCTION = 'judge.social_auth.slugify_username'
SOCIAL_AUTH_PROTECTED_USER_FIELDS = ['first_name', 'last_name']

MOSS_API_KEY = None

CELERY_WORKER_HIJACK_ROOT_LOGGER = False

WEBAUTHN_RP_ID = None

GOOGLE_SEARCH_ENGINE_URL = None

DESCRIPTION_MAX_LENGTH = 200

GROUP_PERMISSION_FOR_ORG_ADMIN = 'Org Admin'

if DMOJ_PDF_PDFOID_URL:
    # If a cache is configured, it must already exist and be a directory
    assert DMOJ_PDF_PROBLEM_CACHE is None or os.path.isdir(DMOJ_PDF_PROBLEM_CACHE)
    # If using X-Accel-Redirect, the cache directory must be configured
    assert DMOJ_PDF_PROBLEM_INTERNAL is None or DMOJ_PDF_PROBLEM_CACHE is not None

ACE_DEFAULT_LIGHT_THEME = DMOJ_THEME_DEFAULT_ACE_THEME['light']
ACE_DEFAULT_DARK_THEME = DMOJ_THEME_DEFAULT_ACE_THEME['dark']
# Only allow OAuth login
OAUTH_ONLY = False

try:
    with open(os.path.join(os.path.dirname(__file__), 'local_settings.py')) as f:
        exec(f.read(), globals())
except IOError:
    pass
