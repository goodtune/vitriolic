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
    "constance",
    "constance.backends.database",
    "mptt",
    "cloudinary",
    "guardian",
    "bootstrap3",
    "django_gravatar",
    "embed_video",
    "django_htmx",
    "rest_framework",
    "mcp_server",
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


# Django Constance settings

CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"

CONSTANCE_CONFIG = {
    # Prince PDF Generation
    "PRINCE_SERVER": (None, "Remote server for PDF generation", str),
    "PRINCE_BINARY": ("/usr/local/bin/prince", "Local prince binary path", str),
    "PRINCE_BASE_URL": (None, "Base URL for prince", str),
    # Touch Technology Common
    "TOUCHTECHNOLOGY_APP_ROUTING": ((), "Application routing configuration", tuple),
    "TOUCHTECHNOLOGY_CURRENCY_ABBREVIATION": ("AUD", "Currency code", str),
    "TOUCHTECHNOLOGY_CURRENCY_SYMBOL": ("$", "Currency symbol", str),
    "TOUCHTECHNOLOGY_PAGINATE_BY": (5, "Pagination size", int),
    "TOUCHTECHNOLOGY_PROFILE_FORM_CLASS": (
        "touchtechnology.common.forms_lazy.ProfileForm",
        "Profile form class path",
        str,
    ),
    "TOUCHTECHNOLOGY_SITEMAP_CACHE_DURATION": (None, "Sitemap cache duration", int),
    "TOUCHTECHNOLOGY_SITEMAP_EDIT_PARENT": (False, "Sitemap edit parent flag", bool),
    "TOUCHTECHNOLOGY_SITEMAP_HTTPS_OPTION": (False, "Use HTTPS in sitemap", bool),
    "TOUCHTECHNOLOGY_SITEMAP_ROOT": (None, "Sitemap root node", str),
    "TOUCHTECHNOLOGY_STORAGE_FOLDER": (None, "Storage folder path", str),
    "TOUCHTECHNOLOGY_STORAGE_URL": (None, "Storage URL", str),
    # Touch Technology Content
    "TOUCHTECHNOLOGY_NODE_CACHE": ("default", "Cache backend for nodes", str),
    "TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS": (1, "Number of content blocks", int),
    "TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES": (
        ("copy",),
        "CSS classes for content",
        tuple,
    ),
    "TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE": (None, "Base template path", str),
    "TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER": (
        "touchtechnology/content/pages/",
        "Template folder path",
        str,
    ),
    "TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX": (r"\.html$", "Template regex pattern", str),
    "TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC": (True, "Media public flag", bool),
    # Touch Technology News
    "TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS": ({}, "Detail image kwargs", dict),
    "TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS": (
        (("pilkit.processors.resize.SmartResize", (320, 240), {}),),
        "Detail image processors",
        tuple,
    ),
    "TOUCHTECHNOLOGY_NEWS_PAGINATE_BY": (5, "Pagination for news", int),
    "TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS": ({}, "Thumbnail image kwargs", dict),
    "TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS": (
        (("pilkit.processors.resize.SmartResize", (160, 120), {}),),
        "Thumbnail image processors",
        tuple,
    ),
    # Tournament Control Competition
    "TOURNAMENTCONTROL_COMPETITION_VIDEOS_ARRAY_SIZE": (
        5,
        "Array size for videos",
        int,
    ),
    "TOURNAMENTCONTROL_SCORECARD_PDF_WAIT": (5, "PDF wait time in seconds", int),
    "TOURNAMENTCONTROL_ASYNC_PDF_GRID": (False, "Enable async PDF grid generation", bool),
    # Other
    "FROALA_EDITOR_OPTIONS": ({}, "Froala editor configuration", dict),
    "GOOGLE_ANALYTICS": (None, "Google Analytics tracking code", str),
    "ANONYMOUS_USER_ID": (None, "Anonymous user ID", int),
}


# Django MCP Server settings

DJANGO_MCP_GLOBAL_SERVER_CONFIG = {
    "name": "vitriolic-mcp-server",
    "instructions": "MCP Server for Tournament Control Competition Management System. Provides access to clubs, competitions, seasons, divisions, stages, teams, matches, and players data.",
}

# Optional: Configure authentication for MCP endpoints
# DJANGO_MCP_AUTHENTICATION_CLASSES = ["rest_framework.authentication.SessionAuthentication"]
