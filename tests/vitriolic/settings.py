"""
Django settings for vitriolic project.
"""

import os
import time

import environ
from django.urls import reverse_lazy

env = environ.Env()

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SILENCED_SYSTEM_CHECKS = env.list("SILENCED_SYSTEM_CHECKS", default=[])
SILENCED_SYSTEM_CHECKS.append("models.E006")

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.10/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "3h_k7=3wv&i&#^36t=zv)l99bijpp06j((ld%7u7&3u)2!8iq8"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Test mode flag - used by admin component registration to allow re-registration
TESTING = True

ALLOWED_HOSTS = []

SITE_ID = 1


# Application definition

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.humanize",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "mptt",
    "cloudinary",
    "guardian",
    "bootstrap3",
    "django_gravatar",
    "embed_video",
    "django_htmx",
    "rest_framework",
    "oauth2_provider",
    "touchtechnology.common",
    "touchtechnology.admin",
    "touchtechnology.content",
    "touchtechnology.news",
    "tournamentcontrol.competition",
    "example_app",
]

MIDDLEWARE = [
    "django.contrib.sites.middleware.CurrentSiteMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "touchtechnology.common.middleware.served_by_middleware",
    "touchtechnology.content.middleware.SitemapNodeMiddleware",
    "touchtechnology.content.middleware.redirect_middleware",
]

ROOT_URLCONF = "vitriolic.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # It would be better if we could use modify_settings to append
                # these as required, but all the core Django checks look like
                # overriding TEMPLATES is done as override_settings and done
                # in entirety.
                "touchtechnology.common.context_processors.env",
                "touchtechnology.common.context_processors.query_string",
                "touchtechnology.common.context_processors.site",
                "touchtechnology.common.context_processors.tz",
                # Static files context processor
                "django.template.context_processors.static",
            ],
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        },
    },
]

WSGI_APPLICATION = "vitriolic.wsgi.application"


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    "default": env.db(default="psql://vitriolic:vitriolic@localhost/vitriolic"),
}

if DATABASES["default"]["ENGINE"].startswith("django.db.backends.postgresql"):
    DATABASES["default"]["PORT"] = env.int("DB_5432_TCP_PORT", default=5432)
    # delay long enough to let the postgresql container startup
    time.sleep(4)


# Password validation
# https://docs.djangoproject.com/en/1.10/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"  # noqa: E501
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Use modern, secure password hashers. MD5PasswordHasher was used previously for
# test speed but using production-grade hashers ensures compatibility with Django 4.0+
# and prevents ImportError with deprecated hashers like SHA1PasswordHasher.
# PBKDF2PasswordHasher is Django's default and provides good security.
# PBKDF2SHA1PasswordHasher is included for backward compatibility with older passwords.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",  # this is default
    "guardian.backends.ObjectPermissionBackend",
    # Bearer tokens issued by the OAuth 2.0 provider identify MCP clients.
    "oauth2_provider.backends.OAuth2Backend",
)

LOGIN_URL = reverse_lazy("accounts:login")

ANONYMOUS_USER_NAME = "anonymous"


# Internationalization
# https://docs.djangoproject.com/en/1.10/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.10/howto/static-files/

STATIC_URL = "/static/"


# OAuth2

GOOGLE_OAUTH2_CLIENT_ID = ""
GOOGLE_OAUTH2_CLIENT_SECRET = ""


# Run Celery tasks inline during the test suite so they execute synchronously
# against the same database/transactional context as the calling code.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True


# Logging setup. Adjust handlers as required.

LOGGING = {
    "version": 1,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "null": {"class": "logging.NullHandler"},
    },
    "loggers": {
        "": {"level": "DEBUG", "handlers": ["null"]},
    },
}


# Touch Technology settings

TOUCHTECHNOLOGY_SITEMAP_ROOT = "home"


# MCP server settings

TOURNAMENTCONTROL_MCP_NAME = "vitriolic"
TOURNAMENTCONTROL_MCP_INSTRUCTIONS = (
    "MCP server for the Tournament Control competition management system."
)
TOURNAMENTCONTROL_MCP_ADMIN_NAME = "vitriolic-admin"


# OAuth 2.1 authorization server for MCP clients (django-oauth-toolkit).
# See docs/mcp-admin.md.

OAUTH2_PROVIDER = {
    "PKCE_REQUIRED": True,
    "COMPLIANT_BCP_RFC9700_PKCE_METHOD": True,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
    "SCOPES": {
        "competition": "Read and administer competitions on your behalf",
    },
    "DEFAULT_SCOPES": ["competition"],
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,
    "ROTATE_REFRESH_TOKEN": True,
    # Public clients (Claude Code, Claude.ai) authenticate with PKCE alone.
    "OAUTH2_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED": [
        "none",
        "client_secret_post",
        "client_secret_basic",
    ],
    "DCR_ENABLED": True,
    "DCR_REGISTRATION_PERMISSION_CLASSES": (
        "oauth2_provider.dcr.AllowAllDCRPermission",
    ),
    "OAUTH2_PROTECTED_RESOURCE_NAME": "Tournament Control",
}
