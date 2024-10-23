import logging
import datetime
from traceback import print_exc

from django.core.cache import cache
from django.conf import settings
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from huey import crontab, CancelExecution
from huey.contrib.djhuey import db_periodic_task, db_task, lock_task, HUEY

from google_indexer.apps.indexer.exceptions import ApiKeyExpired, ApiKeyInvalid
from google_indexer.apps.indexer.models import SITE_STATUS_CREATED, SITE_STATUS_OK, TrackedSite, TrackedPage, \
    PAGE_STATUS_INDEXED, PAGE_STATUS_NEED_INDEXATION, SITE_STATUS_PENDING, \
    PAGE_STATUS_PENDING_INDEXATION_CALL, \
    APIKEY_INVALID, APIKEY_USAGE_INDEXATION, SITE_STATUS_HOLD, CallError
from google_indexer.apps.indexer.utils import fetch_sitemap_links, call_indexation, \
    get_available_apikey, has_available_apikey
import time

# our stuff

WAIT_REINDEX_PAGES_DAYS = settings.WAIT_REINDEX_PAGES_DAYS
WAIT_REINDEX_SITEMAP_DAYS = settings.WAIT_REINDEX_SITEMAP_DAYS
WAIT_BETWEEN_VALIDATION_SECONDS = settings.WAIT_BETWEEN_VALIDATION_SECONDS

logger = logging.getLogger(__name__)


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


## note :

# periodic_task take parameters as described in https://huey.readthedocs.io/en/latest/guide.html#periodic-tasks


@db_periodic_task(crontab(minute="*"))  # On execute toute les minutes au lieu de 5 */5.
def index_pages():
    max_pending = 600 # on essaye une valeur à la main (60 / WAIT_BETWEEN_VALIDATION_SECONDS) * 5.
    chunk_size = max(0, max_pending - TrackedPage.objects.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).count())
    now = timezone.now()
    if not has_available_apikey(now):
        print("no more available apikeys for today, skipping execution")
        return

    with (transaction.atomic()):

        # try to find if there is new pages
        filtered_page_queryset = TrackedPage.objects.filter(
            status=PAGE_STATUS_NEED_INDEXATION,
        ).exclude(site__status=SITE_STATUS_HOLD).order_by(
            F("last_indexation").asc(nulls_first=True)
        )

        if not filtered_page_queryset.exists():
            # if there is no new pages, we reindex the already indexed ones that is older than WAIT_REINDEX_PAGES_DAYS
            last_validation_reindex = timezone.now() - datetime.timedelta(days=WAIT_REINDEX_PAGES_DAYS)
            print("no new page, trying to find old indexed pages indexed before %s" % last_validation_reindex)
            filtered_page_queryset = TrackedPage.objects.filter(
                status=PAGE_STATUS_INDEXED,
                last_indexation__lte=last_validation_reindex
            ).exclude(site__status=SITE_STATUS_HOLD).order_by(
                F("last_indexation").asc(nulls_first=True)
            )

        id_page_to_update = list(
            filtered_page_queryset.select_for_update(skip_locked=True).values_list('id', flat=True)[:chunk_size]
        )

        TrackedPage.objects.filter(pk__in=id_page_to_update).update(
            status=PAGE_STATUS_PENDING_INDEXATION_CALL,
            last_indexation=now
        )
        print("found %d pages to reindex" % (len(id_page_to_update), ))

    for page_id in id_page_to_update:
        index_page(page_id)


@lock_task('refresh_sitemap')  # Goes *after* the task decorator.
@db_periodic_task(crontab(minute="*/5"))
def refresh_sitemap():
    print("will refresh_sitemap")

    site_to_update = []
    with transaction.atomic():
        for site in TrackedSite.objects.select_for_update().filter(
                Q(status=SITE_STATUS_CREATED) | (Q(status=SITE_STATUS_OK) & (Q(next_update__lte=timezone.now())| Q(next_update__isnull=True)))):
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
    print("created %d pages" % len(total))

    for chunk in chunks(to_delete, 50):
        deleted = site.pages.filter(url__in=chunk).delete()
        print("deleted", deleted)

    with transaction.atomic():
        site = TrackedSite.objects.select_for_update().filter(pk=site_id).get()
        site.status = SITE_STATUS_OK
        site.last_update = timezone.now()
        site.next_update = timezone.now() + datetime.timedelta(days=WAIT_REINDEX_SITEMAP_DAYS)
        site.save()


@db_task(retries=2)
def index_page(page_id):
    end_throttle = time.time() + WAIT_BETWEEN_VALIDATION_SECONDS  # one check per 2 second max
    retry = False
    with transaction.atomic():
        print("indexing page ", page_id)
        page: TrackedPage = TrackedPage.objects.filter(id=page_id).select_for_update().first()

        if page is None or page.status != PAGE_STATUS_PENDING_INDEXATION_CALL:
            print("page is not marked for indexation. skipping")
            raise CancelExecution(retry=False)
        # this call may take some time, and will call heavy stuff
        apikey = get_available_apikey(timezone.now(), APIKEY_USAGE_INDEXATION)
        print("got key", apikey)
        if apikey is None:
            # page will be checked later
            page.status = PAGE_STATUS_NEED_INDEXATION
            page.save()

            print("no more api key available. no indexation until next availability occurs")
        error = None
        try:
            call_indexation(page.url, apikey)
            print("indexation call done")
        except ApiKeyExpired:
            print("api key expired")
            error = "Api Key Expired"
            apikey.count_of_the_day = apikey.max_per_day + 1
            apikey.save()
            
            retry = True
        except ApiKeyInvalid:
            error = "Api key Invalid"
            print("api key invalid")
            apikey.status = APIKEY_INVALID
            apikey.save()
            retry = True
        except Exception as e:
            print("got exception")
            error = "exception : %s" % traceback.format_exc()
            print_exc()
        else:
            page.status = PAGE_STATUS_INDEXED
            page.last_indexation = timezone.now()
            page.save()
            print("page saved.")
        if error:
            CallError.objects.create(api_key=apikey, page=page, site=page.site, error=error)
    remaining = end_throttle - time.time()
    if remaining > 0:
        time.sleep(remaining)
  # Log the number of remaining tasks in the queue
    remaining_tasks = len(HUEY.pending())
    print(f"Nombre de tâches restantes dans la file d'attente : {remaining_tasks}")
    if retry:
        raise CancelExecution()

