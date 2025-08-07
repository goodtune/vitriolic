"""Django settings for E2E testing."""
import os
from pathlib import Path

# Import base test settings
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from vitriolic.settings import *

# Override settings for E2E testing
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "vitriolic_e2e",
        "USER": "vitriolic",
        "PASSWORD": "vitriolic", 
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# Redis for Celery
REDIS_URL = "redis://localhost:6379/1"

# Celery configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False  # Run async for E2E tests

# Cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = Path(__file__).parent / "static"

# Media files  
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(__file__).parent / "media"

# Disable migrations for faster test setup
MIGRATION_MODULES = {
    app: None for app in [
        "admin", "auth", "contenttypes", "sessions", "messages", "staticfiles",
        "sites", "touchtechnology.common", "touchtechnology.admin", 
        "touchtechnology.content", "touchtechnology.news",
        "tournamentcontrol.competition"
    ]
}