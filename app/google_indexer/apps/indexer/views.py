from django.shortcuts import render
from django.views.generic import ListView

from google_indexer.apps.indexer.models import TrackedWebsite


# Create your views here.


class TrackedSiteListView(ListView):
    model = TrackedWebsite

