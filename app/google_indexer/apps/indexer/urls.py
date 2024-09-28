from django.urls import path
from .views import TrackedSiteListView
app_name = "indexer"
urlpatterns = [
    path("list/", TrackedSiteListView.as_view(), name="site-list"),
]