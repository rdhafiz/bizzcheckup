"""python manage.py make_seo_images: draw the site's share picture and home-screen icon.

- static/img/og-image.png (1200 x 630): shown when someone shares the homepage on
  Facebook, LinkedIn, WhatsApp or X (the og:image in core/seo.py).
- static/img/apple-touch-icon.png (180 x 180): the icon when the site is added to a
  phone's home screen.

Both are drawn from templates/core/og_image.html in the same offline Chromium as the PDF
and the share card. They're committed to git; run this again after changing that page.
"""

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from bizzcheckup.core.views import check_count
from bizzcheckup.reports.pdf import static_file
from bizzcheckup.reports.share_card import html_to_png

# The example score bars on the picture: (label, width in %, colour).
EXAMPLE_SIGNS = [
    ("Performance", 88, "#31ac64"),
    ("Accessibility", 96, "#31ac64"),
    ("Security", 92, "#31ac64"),
    ("Google", 94, "#31ac64"),
    ("AI readiness", 81, "#f5b544"),
]
IMAGES = [  # (file name, width, height, draw the icon?)
    ("og-image.png", 1200, 630, False),
    ("apple-touch-icon.png", 180, 180, True),
]


class Command(BaseCommand):
    help = "Draw static/img/og-image.png and static/img/apple-touch-icon.png."

    def handle(self, *args: Any, **options: Any) -> None:
        folder = Path(settings.BASE_DIR) / "static" / "img"
        for name, width, height, icon in IMAGES:
            html = render_to_string(
                "core/og_image.html",
                {
                    "width": width,
                    "height": height,
                    "icon": icon,
                    "check_count": check_count(),
                    "signs": EXAMPLE_SIGNS,
                    "site_host": urlsplit(str(settings.SITE_URL)).netloc,
                },
            )
            png = async_to_sync(html_to_png)(html, static_file, width=width, height=height)
            (folder / name).write_bytes(png)
            self.stdout.write(self.style.SUCCESS(f"Wrote static/img/{name} ({len(png)} bytes)"))
