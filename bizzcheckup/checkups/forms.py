from asgiref.sync import async_to_sync
from django import forms

from bizzcheckup.engine.netguard import BlockedURLError
from bizzcheckup.engine.urls import InvalidURLError, normalize_url, site_root

from . import services


class CheckupForm(forms.Form):
    """The landing-page form: website address, optional contact details, consent."""

    page_dropped = False  # set by clean_url: the visitor entered one page's address

    # A CharField, not URLField: visitors type "myshop.com" without https://.
    url = forms.CharField(label="Your website address", max_length=2048)
    name = forms.CharField(label="Your name", max_length=120, required=False)
    email = forms.EmailField(label="Your email", required=False)
    consent = forms.BooleanField(
        label="I agree to the privacy note",
        error_messages={"required": "Please agree to the privacy note to start your check-up."},
    )

    # Honeypot: hidden from people with CSS, but bots that fill in every field fill this
    # one too. A real visitor leaves it empty.
    website = forms.CharField(required=False, label="Leave this field empty")

    def clean_url(self) -> str:
        try:
            entered = normalize_url(self.cleaned_data["url"])
        except InvalidURLError as error:
            raise forms.ValidationError(str(error)) from error
        # Free check-ups cover the website from its main address, never one chosen page.
        url = site_root(entered)
        self.page_dropped = entered != url
        try:
            # SSRF protection right away: never queue an internal address.
            async_to_sync(services.make_guard().check_url)(url)
        except BlockedURLError as error:
            raise forms.ValidationError(str(error)) from error
        return url

    def clean_name(self) -> str:
        return " ".join(self.cleaned_data["name"].split())  # tidy extra spaces

    @property
    def is_bot(self) -> bool:
        return bool(self.cleaned_data.get("website"))
