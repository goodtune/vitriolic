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

ALLOWED_HOSTS = []

SITE_ID = 1


class DisableMigrations(object):
    """
    Disable the database migrations machinery to speed up test suite.

    Trick learned at http://bit.ly/2vjVpNc
    """

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()


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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",  # this is default
    "guardian.backends.ObjectPermissionBackend",
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
