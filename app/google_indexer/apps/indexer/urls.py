from django.urls import path
from google_indexer.apps.indexer.views.tracked_site import TrackedSiteListView, TrackedSiteDetailView, \
    TrackedSiteDeleteView, TrackedPageActionView
from google_indexer.apps.indexer.views.api_key import ApiKeyListView, ApiKeyDeleteView

app_name = "indexer"
urlpatterns = [
    path("site/", TrackedSiteListView.as_view(), name="site-list"),
    path("site/<int:pk>/", TrackedSiteDetailView.as_view(), name="site-detail"),
    path("site/<int:pk>/delete", TrackedSiteDeleteView.as_view(), name="site-delete"),

    path("page/<int:pk>/action", TrackedPageActionView.as_view(), name="page-action"),
    path("apikey/", ApiKeyListView.as_view(), name="apikey-list"),
    path("apikey/<int:pk>/delete", ApiKeyDeleteView.as_view(), name="apikey-delete"),

]