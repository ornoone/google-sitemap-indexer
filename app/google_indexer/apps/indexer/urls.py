from django.urls import path
from .views import TrackedSiteListView, TrackedSiteDetailView, ApiKeyListView, ApiKeyDeleteView

app_name = "indexer"
urlpatterns = [
    path("site/", TrackedSiteListView.as_view(), name="site-list"),
    path("site/<int:pk>/", TrackedSiteDetailView.as_view(), name="site-detail"),
    path("apikey/", ApiKeyListView.as_view(), name="apikey-list"),
    path("apikey/<int:pk>/delete", ApiKeyDeleteView.as_view(), name="apikey-delete"),

]