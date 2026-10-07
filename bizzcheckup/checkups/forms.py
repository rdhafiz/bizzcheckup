from asgiref.sync import async_to_sync
from django import forms

from bizzcheckup.engine.netguard import BlockedURLError
from bizzcheckup.engine.urls import InvalidURLError, normalize_url

from . import services


class CheckupForm(forms.Form):
    """The landing-page form. (Name, email and consent arrive in phase 9.)"""

    # A CharField, not URLField: visitors type "myshop.com" without https://.
    url = forms.CharField(label="Your website address", max_length=2048)

    # Honeypot: hidden from people with CSS, but bots that fill in every field fill this
    # one too. A real visitor leaves it empty.
    website = forms.CharField(required=False, label="Leave this field empty")

    def clean_url(self) -> str:
        try:
            url = normalize_url(self.cleaned_data["url"])
        except InvalidURLError as error:
            raise forms.ValidationError(str(error)) from error
        try:
            # SSRF protection right away: never queue an internal address.
            async_to_sync(services.make_guard().check_url)(url)
        except BlockedURLError as error:
            raise forms.ValidationError(str(error)) from error
        return url

    @property
    def is_bot(self) -> bool:
        return bool(self.cleaned_data.get("website"))
