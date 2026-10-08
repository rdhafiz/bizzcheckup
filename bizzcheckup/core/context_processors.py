"""Values every template can use without the view passing them in."""

from django.conf import settings
from django.http import HttpRequest

from bizzcheckup import __version__
from bizzcheckup.reports.branding import Branding, load_branding

PRODUCT_NAME = "BizzCheckup"
TAGLINE = "Check your business's online health"


def brand(request: HttpRequest) -> dict[str, str | Branding]:
    return {
        "branding": load_branding(),  # cached; re-read only when branding.yaml changes
        "product_name": PRODUCT_NAME,
        "tagline": TAGLINE,
        "app_version": __version__,
        "turnstile_site_key": settings.TURNSTILE_SITE_KEY if settings.TURNSTILE_SECRET_KEY else "",
    }
