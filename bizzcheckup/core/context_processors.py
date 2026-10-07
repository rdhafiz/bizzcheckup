"""Values every template can use without the view passing them in."""

from django.http import HttpRequest

from bizzcheckup import __version__

PRODUCT_NAME = "BizzCheckup"
TAGLINE = "Check your business's online health"


def brand(request: HttpRequest) -> dict[str, str]:
    return {
        "product_name": PRODUCT_NAME,
        "tagline": TAGLINE,
        "app_version": __version__,
    }
