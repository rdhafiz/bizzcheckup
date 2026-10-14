"""Settings shared by every environment (dev, test, prod).

Values that change per machine or are secret come from environment variables,
read with django-environ. See docs/06-configuration.md for every variable.
"""

import os
from pathlib import Path

import environ

# config/settings/base.py -> three .parent calls up is the project root.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Read .env if it exists.
# - On a server (Docker, prod): real environment variables win over .env.
# - On your computer (dev settings): .env wins, so an old value left in a terminal
#   (e.g. an empty PSI_API_KEY from before you added it) can't hide the real one.
# - Tests skip .env (see test.py), so local settings can't change test results.
if not os.environ.get("BIZZCHECKUP_IGNORE_DOTENV"):
    developing = os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".dev")
    environ.Env.read_env(BASE_DIR / ".env", overwrite=developing)

# Headless Chromium installed inside the project (start.sh does this), so every process,
# however it was started, uses the same browser. Docker sets its own path instead.
if (BASE_DIR / ".playwright").is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BASE_DIR / ".playwright"))


# --- Core -------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",  # /sitemap.xml (part of Django, no extra package)
    # Before staticfiles so runserver serves files the same way as production.
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Our apps
    "bizzcheckup.core",
    "bizzcheckup.checkups",
    "bizzcheckup.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "bizzcheckup.core.security.SecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "bizzcheckup.core.context_processors.brand",
            ],
        },
    },
]


# --- Database & cache -------------------------------------------------------

# Example: postgres://user:password@host:5432/dbname
DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    # SQLite allows one writer at a time; wait for it instead of failing at once.
    DATABASES["default"].setdefault("OPTIONS", {})["timeout"] = 20
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}


# --- Celery (background jobs) -----------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
# Results are stored on the Checkup model, not in Celery.
CELERY_TASK_IGNORE_RESULT = True
# Take one job at a time and only mark it done after it finishes,
# so a crashed worker doesn't lose a check-up.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
# If Redis is down, give up queueing within about a second instead of hanging the page.
CELERY_TASK_PUBLISH_RETRY_POLICY = {"max_retries": 2, "interval_start": 0, "interval_step": 0.3}
CELERY_BROKER_CONNECTION_TIMEOUT = 2
# Celery Beat (the "clock" container) starts the monthly re-checks that are due.
CELERY_BEAT_SCHEDULE = {
    "monthly-rechecks": {
        "task": "bizzcheckup.checkups.tasks.run_due_rechecks",
        "schedule": 6 * 60 * 60,  # every 6 hours, in seconds
    },
}


# --- Passwords --------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Language & time --------------------------------------------------------

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static files (CSS, JS, fonts, images) ----------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# --- Security defaults (tightened further in prod.py) -----------------------

SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"


# --- BizzCheckup ------------------------------------------------------------

# Google PageSpeed Insights API key. Empty = performance checks are skipped.
PSI_API_KEY = env("PSI_API_KEY", default="")

# Branding that fills the report's cover, proposal and contact pages.
BRANDING_FILE = BASE_DIR / "branding.yaml"

# Audit limits (see docs/14-audit-engine.md).
CHECKUP_MAX_PAGES = env.int("CHECKUP_MAX_PAGES", default=10)
CHECKUP_TIMEOUT_SECONDS = env.int("CHECKUP_TIMEOUT_SECONDS", default=180)
CHECKUP_MAX_PAGE_BYTES = env.int("CHECKUP_MAX_PAGE_BYTES", default=5 * 1024 * 1024)

# Abuse protection (see docs/17-security.md).
CHECKUP_RATE_LIMIT_PER_HOUR = env.int("CHECKUP_RATE_LIMIT_PER_HOUR", default=5)
CHECKUP_QUEUE_CAP = env.int("CHECKUP_QUEUE_CAP", default=20)  # waiting + running, everyone
CHECKUP_REUSE_HOURS = env.int("CHECKUP_REUSE_HOURS", default=24)
# Secret salt for hashing visitor IPs. Defaults to the secret key; set its own value
# in production so rotating the secret key doesn't reset rate limits.
IP_HASH_SALT = env("IP_HASH_SALT", default=SECRET_KEY)
# Only turn on behind a reverse proxy that sets X-Forwarded-For itself.
TRUST_X_FORWARDED_FOR = env.bool("TRUST_X_FORWARDED_FOR", default=False)
# A header holding the visitor's IP that the proxy in front always sets itself, e.g.
# "CF-Connecting-IP" behind Cloudflare. Wins over X-Forwarded-For. Empty = not used.
CLIENT_IP_HEADER = env("CLIENT_IP_HEADER", default="")
# Cloudflare Turnstile "are you human?" check. Off unless both keys are set.
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY", default="")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY", default="")

# --- Email (docs/21-emails.md) ---------------------------------------------------------
# The site's public address, for links in emails (they're sent without a web request, so
# Django can't work it out). No trailing slash.
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")
# Gmail by default: turn on 2-step verification, then create an "app password" at
# https://myaccount.google.com/apppasswords and put it in EMAIL_HOST_PASSWORD.
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = 30  # seconds: a slow connection or mail server must not hang a page forever
# No login yet: print emails in the terminal instead of sending them (handy locally).
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.smtp.EmailBackend"
        if EMAIL_HOST_USER
        else "django.core.mail.backends.console.EmailBackend"
    ),
)
# Gmail only sends "from" the account itself, so that's the default sender.
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default=f"BizzCheckup <{EMAIL_HOST_USER or 'noreply@localhost'}>"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Who gets "new lead" alerts. Empty = the email in branding.yaml.
LEAD_ALERT_EMAIL = env("LEAD_ALERT_EMAIL", default="")
# Also alert for check-ups without contact details whose health score is below this
# (0 = off). Useful to spot sites that need help, but it can be a lot of email.
LEAD_ALERT_LOW_SCORE = env.int("LEAD_ALERT_LOW_SCORE", default=0)
# Monthly re-checks (docs/21-emails.md): how often, and how many may start per run of the
# scheduler (every 6 hours), so they never crowd out visitors' own check-ups.
RECHECK_EVERY_DAYS = env.int("RECHECK_EVERY_DAYS", default=30)
RECHECKS_PER_RUN = env.int("RECHECKS_PER_RUN", default=5)
# "Email me this report": how many times one report can be emailed per day.
REPORT_EMAILS_PER_DAY = env.int("REPORT_EMAILS_PER_DAY", default=3)

# How check-ups run (docs/12-background-jobs.md):
#   "immediate" (default): start straight away inside the web app, no Redis/Celery needed
#   "celery": send them to a separate Celery worker through Redis (for heavy traffic)
CHECKUP_RUNNER = env.str("CHECKUP_RUNNER", default="immediate")
# How many check-ups may run at the same time in one web process ("immediate" mode).
CHECKUP_MAX_CONCURRENT = env.int("CHECKUP_MAX_CONCURRENT", default=3)

# The worker stops a check-up that runs past the timeout, with some extra room.
CELERY_TASK_SOFT_TIME_LIMIT = CHECKUP_TIMEOUT_SECONDS + 30
CELERY_TASK_TIME_LIMIT = CHECKUP_TIMEOUT_SECONDS + 60
