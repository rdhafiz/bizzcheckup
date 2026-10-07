"""Settings for working on your own computer."""

from .base import *  # noqa: F403
from .base import BASE_DIR, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# While developing you start many check-ups yourself; production keeps the default 5.
CHECKUP_RATE_LIMIT_PER_HOUR = env.int("CHECKUP_RATE_LIMIT_PER_HOUR", default=50)

# Write warnings and errors (with tracebacks) to .run/bizzcheckup.log as well as the
# terminal, so problems in check-ups can be read after they happened. Skipped where the
# folder can't be created (e.g. inside the Docker image, which runs as a non-root user).
_handlers = ["console"]
_file_handler: dict[str, object] = {}
try:
    (BASE_DIR / ".run").mkdir(exist_ok=True)
except OSError:
    pass
else:
    _handlers.append("file")
    _file_handler = {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / ".run" / "bizzcheckup.log",
            "maxBytes": 2_000_000,
            "backupCount": 2,
            "encoding": "utf-8",
            "formatter": "plain",
        }
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        **_file_handler,
    },
    "loggers": {
        "bizzcheckup": {"handlers": _handlers, "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "INFO"},
    },
}
