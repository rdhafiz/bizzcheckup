"""Settings for working on your own computer."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# While developing you start many check-ups yourself; production keeps the default 5.
CHECKUP_RATE_LIMIT_PER_HOUR = env.int("CHECKUP_RATE_LIMIT_PER_HOUR", default=50)
