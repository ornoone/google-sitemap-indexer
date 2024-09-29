from django.urls import path
from .views import TrackedSiteListView, TrackedSiteDetailView

app_name = "indexer"
urlpatterns = [
    path("list/", TrackedSiteListView.as_view(), name="site-list"),
    path("detail/<int:pk>/", TrackedSiteDetailView.as_view(), name="site-detail"),
]