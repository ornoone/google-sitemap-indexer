import logging
import datetime
from traceback import print_exc

from django.core.cache import cache
from django.core.cache.backends.redis import RedisCache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from huey import crontab, CancelExecution
from huey.contrib.djhuey import db_periodic_task, db_task, lock_task

from google_indexer.apps.indexer.exceptions import ApiKeyExpired, ApiKeyInvalid
from google_indexer.apps.indexer.models import SITE_STATUS_CREATED, SITE_STATUS_OK, TrackedSite, TrackedPage, \
    PAGE_STATUS_CREATED, PAGE_STATUS_INDEXED, PAGE_STATUS_NEED_INDEXATION, SITE_STATUS_PENDING, \
    PAGE_STATUS_PENDING_VERIFICATION, PAGE_STATUS_PENDING_INDEXATION_CALL, PAGE_STATUS_PENDING_INDEXATION_WAIT, ApiKey, \
    APIKEY_INVALID
from google_indexer.apps.indexer.utils import page_is_indexed, fetch_sitemap_links, call_indexation, \
    get_available_apikey, has_available_apikey
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

## note :

# periodic_task take parameters as described in https://huey.readthedocs.io/en/latest/guide.html#periodic-tasks



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
                Q(next_verification__lte=timezone.now())
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
            last_verification=timezone.now()
        )

    for page_id in id_page_to_update:
        verify_page(page_id)


@lock_task('index_pages')  # Goes *after* the task decorator.
@db_periodic_task(crontab(minute="*/5"))
def index_pages():

    max_pending = (60 / WAIT_BETWEEN_VALIDATION_SECONDS) * 5
    chunk_size = max_pending - TrackedPage.objects.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).count()
    now = timezone.now()
    if not has_available_apikey(now):
        print("no more available apikeys for today, skipping execution")
        return
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
            last_indexation=now
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

            print("going to update site ", site.id)
            site.status = SITE_STATUS_PENDING
            site.save()
            site_to_update.append(site)

    for site in site_to_update:
        update_sitemap(site.id)


@db_task()
def update_sitemap(site_id):
    print("start to update sitemap")
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
    existing_urls = set(site.pages.all().values_list("url", flat=True))


    to_create = final_urls - existing_urls

    to_delete = existing_urls - final_urls

    print("to create %s" % len(to_create))
    print("to delete %s" % len(to_delete))
    total = TrackedPage.objects.bulk_create([
        TrackedPage(site=site,
                    url=url)
        for url in to_create
    ])
    print("created %d pages" % total)

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
    print("getting lock")

    with cache.lock('verification_lock', timeout=4, blocking_timeout=8):
        print("lock obtained")
        with transaction.atomic():
            page: TrackedPage = TrackedPage.objects.filter(id=page_id).select_for_update().first()

            if page is None or page.status not in (PAGE_STATUS_PENDING_VERIFICATION, PAGE_STATUS_PENDING_INDEXATION_WAIT):
                print("page is not marked for verification. skipping")
                return
            # this call may take some time, and will call heavy stuff
            if page_is_indexed(page.url):
                print("page %s is indexed" % page.url)
                page.status = PAGE_STATUS_INDEXED
                page.next_verification = timezone.now() + datetime.timedelta(days=WAIT_VALIDATE_INDEXED_PAGE_DAYS)

            else:
                print("page %s is not indexed"% page.url)
                page.status = PAGE_STATUS_NEED_INDEXATION
            page.last_verification = timezone.now()
            page.save()
        # held the lock until the next usage of the resource can be done
        time.sleep(end_throttle - time.time())


@db_task(retries=2)
def index_page(page_id):
    end_throttle = time.time() + WAIT_BETWEEN_VALIDATION_SECONDS  # one check per 2 second max
    retry = False
    with cache.lock('verification_lock'):
        with transaction.atomic():
            print("indexing page ", page_id)
            page: TrackedPage = TrackedPage.objects.filter(id=page_id).select_for_update().first()

            if page is None or page.status != PAGE_STATUS_PENDING_VERIFICATION:
                print("page is not marked for indexation. skipping")
                raise CancelExecution(retry=False)
            # this call may take some time, and will call heavy stuff
            apikey = get_available_apikey(timezone.now())
            print("got key", apikey)
            if apikey is None:
                # page will be checked later
                page.status = PAGE_STATUS_NEED_INDEXATION
                page.save()
                raise Exception("no more api key available")

            try:
                call_indexation(page.url, apikey)
                print("indexation call done")
            except ApiKeyExpired:
                apikey.count_of_the_day = apikey.max_per_day + 1
                apikey.save()
                retry = True
            except ApiKeyInvalid:
                apikey.status = APIKEY_INVALID
                apikey.save()
                retry = True
            except Exception as e:
                print_exc()
            else:
                page.status = PAGE_STATUS_PENDING_INDEXATION_WAIT
                page.next_verification = timezone.now() + datetime.timedelta(days=WAIT_VALIDATE_AFTER_INDEXATION_DAYS)
                page.last_indexation = timezone.now()
                page.save()
                print("page saved.")
        # held the lock until the next usage of the resource can be done
        time.sleep(end_throttle - time.time())

    if retry:
        raise CancelExecution()
