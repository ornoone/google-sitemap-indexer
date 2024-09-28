from django.forms import ModelForm

from google_indexer.apps.indexer.models import TrackedSite


class TrackedSiteForm(ModelForm):

    class Meta:

        model = TrackedSite
        fields = (
            "name",
            "sitemap_url",
        )
