from django import forms

from bizzcheckup.engine.urls import InvalidURLError, normalize_url


class CheckupForm(forms.Form):
    """The landing-page form. (Lead capture, consent and bot protection: phase 9.)"""

    # A CharField, not URLField: visitors type "myshop.com" without https://.
    url = forms.CharField(
        label="Your website address",
        max_length=2048,
        widget=forms.TextInput(
            attrs={
                "placeholder": "yourbusiness.com",
                "autocomplete": "url",
                "inputmode": "url",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )

    def clean_url(self) -> str:
        try:
            return normalize_url(self.cleaned_data["url"])
        except InvalidURLError as error:
            raise forms.ValidationError(str(error)) from error
