
from django.db import models
from django.db.models import Count
from django.utils import timezone

# Create your models here.
SITE_STATUS_CREATED = "CREATED"
SITE_STATUS_PENDING = "PENDING"
SITE_STATUS_HOLD = 'HOLD'
SITE_STATUS_OK = "OK"

# Create your models here.
PAGE_STATUS_NEED_INDEXATION = "2_NEED_INDEXATION"
PAGE_STATUS_PENDING_INDEXATION_CALL = "3_PENDING_INDEXATION_CALL"
PAGE_STATUS_INDEXED = "5_INDEXED"


class TrackedSite(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    sitemap_url = models.URLField(null=False, blank=False)
    status = models.CharField(max_length=255, choices=[
        (SITE_STATUS_CREATED, "created"),
        (SITE_STATUS_PENDING, "pending"),
        (SITE_STATUS_HOLD, "hold"),
        (SITE_STATUS_OK, "up to date"),
    ], default=SITE_STATUS_CREATED)

    next_update = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(null=True, blank=True)

    next_verification = models.DateTimeField(null=True, blank=True)

    def get_pages_statistics(self):
        status_list = self.pages.values('status').annotate(total=Count("status")).order_by("-status")
        status_to_lib = dict(TrackedPage._meta.get_field('status').flatchoices)
        status_dict_label = {status_to_lib.get(record['status'], record['status']): record['total'] for record in status_list}
        status_dict = {record['status']: record['total'] for record in status_list}
        total = self.pages.count()
        status_percent_dict = {record['status']: record['total'] / total * 100 for record in status_list}
        return {
            "total": total,
            "by_statuses": status_dict,
            "by_statuses_label": status_dict_label,
            "by_statuses_percent": status_percent_dict,
        }

    def __str__(self):
        return self.name

class TrackedPage(models.Model):
    site = models.ForeignKey(TrackedSite, on_delete=models.CASCADE, null=False, related_name="pages")
    url = models.URLField(null=False, blank=False)

    # FSM:
    # created ->  .....................................................................  |-> indexed
    #         |-> need indexation -> pending indextation call -> pending indexation wait |


    status = models.CharField(max_length=255, choices=[
        (PAGE_STATUS_NEED_INDEXATION, "need indexation"),
        (PAGE_STATUS_PENDING_INDEXATION_CALL, "pending indexation call"),
        (PAGE_STATUS_INDEXED, "indexed"),
    ], default=PAGE_STATUS_NEED_INDEXATION)

    last_indexation = models.DateTimeField(null=True, blank=True)


APIKEY_VALID = "VALID"
APIKEY_INVALID = "INVALID"

APIKEY_USAGE_INDEXATION = 'APIKEY_USAGE_INDEXATION'
APIKEY_USAGE_VERIFICATION = 'APIKEY_USAGE_VERIFICATION'

class ApiKey(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)

    status = models.CharField(max_length=255, choices=[
        (APIKEY_VALID, "valid"),
        (APIKEY_INVALID, "invalid"),
    ], default=APIKEY_VALID)

    usage = models.CharField(max_length=255, null=False, blank=False, default=APIKEY_USAGE_INDEXATION, choices=[
        (APIKEY_USAGE_INDEXATION, "⚡Indexing"),
         (APIKEY_USAGE_VERIFICATION, "✅Checking"),
    ])

    content = models.JSONField(null=False, blank=False)
    last_usage = models.DateTimeField(null=True, blank=True)
    count_of_the_day = models.IntegerField(default=0)
    max_per_day = models.IntegerField(default=200)


    def __str__(self):
        return f"ApiKey {self.id}. {self.last_usage} for {self.count_of_the_day}/{self.max_per_day}"

    def count_today(self):
        if self.last_usage is None:
            return 0
        elif self.last_usage.date() == timezone.now().date():
            return self.count_of_the_day
        else:
            return 0