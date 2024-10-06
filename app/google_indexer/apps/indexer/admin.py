from django.contrib import admin

from google_indexer.apps.indexer.models import TrackedSite, ApiKey, TrackedPage


# Register your models here.


@admin.register(TrackedSite)
class TrackedSiteAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sitemap_url",
        "status",
        "next_update",
        "last_update",
    )


@admin.register(TrackedPage)
class TrackedPageAdmin(admin.ModelAdmin):
    list_display = (
        "site",
        "url",
        "status",
        "next_verification",
        "last_verification",
        "last_indexation",
    )


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name",
                    "status",
                    "usage",
                    "last_usage",
                    "count_of_the_day",
                    "max_per_day",

                    )
