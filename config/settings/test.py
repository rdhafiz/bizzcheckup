"""Settings for the automated tests (pytest).

Tests must run without Docker: SQLite and an in-memory cache are used unless
DATABASE_URL is set (CI sets it to a real PostgreSQL).
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")

from .base import *  # noqa: E402, F403

DEBUG = False

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Hashing passwords properly is slow on purpose; tests don't need that.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Run Celery tasks immediately inside the test instead of sending them to a worker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Don't need collectstatic for tests.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
