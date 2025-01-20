from django.contrib import admin

from google_indexer.apps.indexer.models import TrackedSite, ApiKey, TrackedPage, CallError


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
        "last_indexation",
    )

    search_fields = (
        "site",
        "status",
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

    search_fields = (
        "name",
        "status",
        "last_usage"
    )

@admin.register(CallError)
class CallErrorAdmin(admin.ModelAdmin):
    list_display = ("date", "api_key", "page", "site")
    readonly_fields = ("api_key", "date", "page", "site")

    actions = ["silent_delete"]

    def silent_delete(self, request, queryset):
        queryset.delete()