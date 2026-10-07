"""Settings for working on your own computer."""

from .base import *  # noqa: F403
from .base import BASE_DIR, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# While developing you start many check-ups yourself; production keeps the default 5.
CHECKUP_RATE_LIMIT_PER_HOUR = env.int("CHECKUP_RATE_LIMIT_PER_HOUR", default=50)

# Write warnings and errors (with tracebacks) to .run/bizzcheckup.log as well as the
# terminal, so problems in check-ups can be read after they happened.
(BASE_DIR / ".run").mkdir(exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / ".run" / "bizzcheckup.log",
            "maxBytes": 2_000_000,
            "backupCount": 2,
            "encoding": "utf-8",
            "formatter": "plain",
        },
    },
    "loggers": {
        "bizzcheckup": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "INFO"},
    },
}
