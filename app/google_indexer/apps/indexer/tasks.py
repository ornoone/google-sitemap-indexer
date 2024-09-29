import logging
import datetime

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task, lock_task

from google_indexer.apps.indexer.models import SITE_STATUS_CREATED, SITE_STATUS_OK, TrackedSite, TrackedPage, \
    PAGE_STATUS_CREATED, PAGE_STATUS_INDEXED, PAGE_STATUS_NEED_INDEXATION, SITE_STATUS_PENDING, \
    PAGE_STATUS_PENDING_VERIFICATION, PAGE_STATUS_PENDING_INDEXATION_CALL, PAGE_STATUS_PENDING_INDEXATION_WAIT
from google_indexer.apps.indexer.utils import page_is_indexed, fetch_sitemap_links, call_indexation, \
    get_available_apikey
import time

# our stuff

WAIT_BETWEEN_VALIDATION_SECONDS = 2  # second
WAIT_VALIDATE_AFTER_INDEXATION_DAYS = 3 # days
WAIT_VALIDATE_INDEXED_PAGE_DAYS = 15 # days
WAIT_REINDEX_SITEMAP_DAYS = 1

logger = logging.getLogger(__name__)


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


@lock_task('verify_stale_pages')  # Goes *after* the task decorator.
@db_periodic_task(crontab(minute="*/5"))
def verify_stale_pages():
    """
    search through the database to find the stale pages, and add a task to update them later
    """

    max_pending = (60 / WAIT_BETWEEN_VALIDATION_SECONDS) * 5
    filtered_page_queryset = TrackedPage.objects.filter(
        Q(
            status=PAGE_STATUS_CREATED
        ) | (
                Q(status=PAGE_STATUS_INDEXED) &
                Q(next_update__lte=timezone.now())
        )
    )
    # compute how many more page we can mark as pending
    chunk_size = max_pending - TrackedPage.objects.filter(status=PAGE_STATUS_PENDING_VERIFICATION).count()

    with transaction.atomic():


        id_page_to_update = list(
            filtered_page_queryset.select_for_update(skip_locked=True).values_list('id',flat=True)[:chunk_size]
        )

        TrackedPage.objects.filter(pk__in=id_page_to_update).update(
            status=PAGE_STATUS_PENDING_VERIFICATION,
            last_updated=timezone.now()
        )

    for page_id in id_page_to_update:
        verify_page(page_id)


@lock_task('index_pages')  # Goes *after* the task decorator.
@db_periodic_task(crontab(minute="*/5"))
def index_pages():

    max_pending = (60 / WAIT_BETWEEN_VALIDATION_SECONDS) * 5
    chunk_size = max_pending - TrackedPage.objects.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).count()
    with transaction.atomic():
        filtered_page_queryset = TrackedPage.objects.filter(
            Q(
                status=PAGE_STATUS_NEED_INDEXATION
            )
        )

        id_page_to_update = list(
            filtered_page_queryset.select_for_update(skip_locked=True).values_list('id',flat=True)[:chunk_size]
        )

        TrackedPage.objects.filter(pk__in=id_page_to_update).update(
            status=PAGE_STATUS_PENDING_INDEXATION_CALL,
            last_updated=timezone.now()
        )

    for page_id in id_page_to_update:
        index_page(page_id)

@lock_task('refresh_sitemap')  # Goes *after* the task decorator.
@db_periodic_task(crontab(minute="*/5"))
def refresh_sitemap():
    print("will refresh_sitemap")
    site_to_update = []
    with transaction.atomic():
        for site in TrackedSite.objects.select_for_update().filter(
                Q(status=SITE_STATUS_CREATED) | (Q(status=SITE_STATUS_OK) & Q(next_update__lte=timezone.now()))):
            site.status = SITE_STATUS_PENDING
            site.save()
            site_to_update.append(site)

    for site in site_to_update:
        update_sitemap(site.id)


@db_task()
def update_sitemap(site_id):
    with transaction.atomic():
        site = TrackedSite.objects.select_for_update().filter(pk=site_id).get()
        if site.status != SITE_STATUS_PENDING:
            print("site already indexed")
            return

        site.status = SITE_STATUS_PENDING
        site.last_update = timezone.now()

        site.save()

    urls = fetch_sitemap_links(site.sitemap_url)
    final_urls = set(urls)
    existing_urls = set(site.pages.all().values("url"))

    to_create = final_urls - existing_urls

    to_delete = existing_urls - final_urls

    total = TrackedPage.objects.bulk_create([
        TrackedPage(site=site,
                    url=url)
        for url in to_create
    ])
    print("created %s pages", total)

    for chunk in chunks(to_delete, 50):
        deleted = site.pages.filter(url__in=chunk).delete()
        print("deleted", deleted)

    with transaction.atomic():
        site = TrackedSite.objects.select_for_update().filter(pk=site_id).get()
        site.status = SITE_STATUS_OK
        site.last_update = timezone.now()
        site.next_update = timezone.now() + datetime.timedelta(days=WAIT_REINDEX_SITEMAP_DAYS)
        site.save()


@db_task()
def verify_page(page_id):
    end_throttle = time.time() + WAIT_BETWEEN_VALIDATION_SECONDS  # one check per 2 second max
    with cache.lock('verification_lock'):
        with transaction.atomic():
            page: TrackedPage = TrackedPage.objects.filter(id=page_id).select_for_update().first()

            if page is None or page.status not in (PAGE_STATUS_PENDING_VERIFICATION, PAGE_STATUS_PENDING_INDEXATION_WAIT):
                return
            # this call may take some time, and will call heavy stuff
            if page_is_indexed(page.url):
                page.status = PAGE_STATUS_INDEXED
                page.next_verification = timezone.now() + datetime.timedelta(days=WAIT_VALIDATE_INDEXED_PAGE_DAYS)

            else:
                page.status = PAGE_STATUS_NEED_INDEXATION
            page.last_verification = timezone.now()
            page.save()
        # held the lock until the next usage of the resource can be done
        time.sleep(end_throttle - time.time())


@db_task()
def index_page(page_id):
    end_throttle = time.time() + WAIT_BETWEEN_VALIDATION_SECONDS  # one check per 2 second max
    with cache.lock('verification_lock'):
        with transaction.atomic():
            page: TrackedPage = TrackedPage.objects.filter(id=page_id).select_for_update().first()

            if page is None or page.status != PAGE_STATUS_PENDING_VERIFICATION:
                return
            # this call may take some time, and will call heavy stuff
            apikey = get_available_apikey(timezone.now())
            if apikey is None:
                raise Exception("no more api key available")

            call_indexation(page.url, apikey)
            page.status = PAGE_STATUS_PENDING_INDEXATION_WAIT
            page.next_verification = timezone.now() + datetime.timedelta(days=WAIT_VALIDATE_AFTER_INDEXATION_DAYS)
            page.last_verification = timezone.now()
            page.save()
        # held the lock until the next usage of the resource can be done
        time.sleep(end_throttle - time.time())
