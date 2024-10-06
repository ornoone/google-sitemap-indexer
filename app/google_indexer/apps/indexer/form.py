
from django.forms import ModelForm
from django import forms
from google_indexer.apps.indexer.models import TrackedSite, ApiKey


class TrackedSiteForm(ModelForm):

    class Meta:

        model = TrackedSite
        fields = (
            "name",
            "sitemap_url",
        )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


class ApikeyImportForm(forms.Form):

    file = MultipleFileField()
    usage = forms.ChoiceField(choices=ApiKey._meta.get_field('usage').choices)
