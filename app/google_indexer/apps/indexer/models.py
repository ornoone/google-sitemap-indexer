from urllib.parse import urlparse
from django.db import models
from django.db.models import Count
from django.utils import timezone

# Statuts des sites
SITE_STATUS_CREATED = "CREATED"
SITE_STATUS_PENDING = "PENDING"
SITE_STATUS_HOLD = "HOLD"
SITE_STATUS_OK = "OK"

# Statuts des pages
PAGE_STATUS_NEED_INDEXATION = "2_NEED_INDEXATION"
PAGE_STATUS_PENDING_INDEXATION_CALL = "3_PENDING_INDEXATION_CALL"
PAGE_STATUS_INDEXED = "5_INDEXED"

# Statuts des clés API
APIKEY_VALID = "VALID"
APIKEY_INVALID = "INVALID"
APIKEY_USAGE_INDEXATION = 'APIKEY_USAGE_INDEXATION'
APIKEY_USAGE_VERIFICATION = 'APIKEY_USAGE_VERIFICATION'


class TrackedSite(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    sitemap_url = models.URLField(null=False, blank=False)
    status = models.CharField(max_length=255, choices=[
        (SITE_STATUS_CREATED, "Created"),
        (SITE_STATUS_PENDING, "Pending"),
        (SITE_STATUS_HOLD, "Hold"),
        (SITE_STATUS_OK, "Up to date"),
    ], default=SITE_STATUS_CREATED)

    next_update = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(null=True, blank=True)
    next_verification = models.DateTimeField(null=True, blank=True)

    def get_pages_statistics(self):
        """Renvoie les statistiques des pages associées au site."""
        status_list = self.pages.values('status').annotate(total=Count("status")).order_by("-status")
        status_to_lib = dict(TrackedPage._meta.get_field('status').flatchoices)
        status_dict_label = {status_to_lib.get(record['status'], record['status']): record['total'] for record in status_list}
        status_dict = {record['status']: record['total'] for record in status_list}
        total = self.pages.count()
        status_percent_dict = {record['status']: (record['total'] / total * 100) if total > 0 else 0 for record in status_list}
        
        return {
            "total": total,
            "by_statuses": status_dict,
            "by_statuses_label": status_dict_label,
            "by_statuses_percent": status_percent_dict,
        }

    def __str__(self):
        return self.name

    def get_favicon_url(self):
        """Renvoie l'URL du favicon pour le site."""
        parsed_url = urlparse(self.sitemap_url)
        domain = parsed_url.netloc
        favicon_url = f"https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://{domain}&size=32"
        return favicon_url

    def get_search_console_url(self):
        """Renvoie l'URL de Google Search Console pour ce domaine."""
        parsed_url = urlparse(self.sitemap_url)
        domain = parsed_url.netloc
        if domain:
            return f"https://search.google.com/search-console?hl=fr&resource_id=sc-domain:{domain}"
        return "#"

    def get_domain_url(self):
        """Renvoie l'URL du domaine à partir de l'URL du sitemap."""
        parsed_url = urlparse(self.sitemap_url)
        domain = parsed_url.netloc
        scheme = parsed_url.scheme
        if domain and scheme:
            return f"{scheme}://{domain}"
        return "#"


class TrackedPage(models.Model):
    site = models.ForeignKey(TrackedSite, on_delete=models.CASCADE, null=False, related_name="pages")
    url = models.URLField(null=False, blank=False)
    
    # Statut de la page
    status = models.CharField(max_length=255, choices=[
        (PAGE_STATUS_NEED_INDEXATION, "Need indexation"),
        (PAGE_STATUS_PENDING_INDEXATION_CALL, "Pending indexation call"),
        (PAGE_STATUS_INDEXED, "Indexed"),
    ], default=PAGE_STATUS_NEED_INDEXATION)

    last_indexation = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"TrackedPage for {self.site.name}: {self.url}"


class ApiKey(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    status = models.CharField(max_length=255, choices=[
        (APIKEY_VALID, "Valid"),
        (APIKEY_INVALID, "Invalid"),
    ], default=APIKEY_VALID)

    usage = models.CharField(max_length=255, null=False, blank=False, choices=[
        (APIKEY_USAGE_INDEXATION, "Indexing"),
        (APIKEY_USAGE_VERIFICATION, "Checking"),
    ], default=APIKEY_USAGE_INDEXATION)

    content = models.JSONField(null=False, blank=False)
    last_usage = models.DateTimeField(null=True, blank=True)
    count_of_the_day = models.IntegerField(default=0)
    max_per_day = models.IntegerField(default=200)

    def __str__(self):
        return f"ApiKey {self.id}: {self.last_usage} for {self.count_of_the_day}/{self.max_per_day}"

    def count_today(self):
        """Renvoie le nombre d'utilisations de la clé API pour aujourd'hui."""
        if self.last_usage is None:
            return 0
        elif self.last_usage.date() == timezone.now().date():
            return self.count_of_the_day
        else:
            return 0

    @classmethod
    def total_usage_counts(cls):
        """Méthode pour calculer le nombre total de clés en fonction de l'usage."""
        total_indexation = cls.objects.filter(usage=APIKEY_USAGE_INDEXATION).count()
        total_check = cls.objects.filter(usage=APIKEY_USAGE_VERIFICATION).count()
        
        return {
            'total_indexation_keys': total_indexation,
            'total_check_keys': total_check,
        }
