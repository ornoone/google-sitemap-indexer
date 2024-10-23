import logging
import datetime
import time
import traceback

from django.core.cache import cache
from django.conf import settings
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from huey import crontab, CancelExecution
from huey.contrib.djhuey import db_periodic_task, db_task, lock_task

from google_indexer.apps.indexer.exceptions import ApiKeyExpired, ApiKeyInvalid
from google_indexer.apps.indexer.models import SITE_STATUS_CREATED, SITE_STATUS_OK, TrackedSite, TrackedPage, \
    PAGE_STATUS_INDEXED, PAGE_STATUS_NEED_INDEXATION, SITE_STATUS_PENDING, \
    PAGE_STATUS_PENDING_INDEXATION_CALL, \
    APIKEY_INVALID, APIKEY_USAGE_INDEXATION, SITE_STATUS_HOLD, CallError
from google_indexer.apps.indexer.utils import fetch_sitemap_links, call_indexation, \
    get_available_apikey, has_available_apikey

logger = logging.getLogger(__name__)

WAIT_REINDEX_PAGES_DAYS = settings.WAIT_REINDEX_PAGES_DAYS
WAIT_REINDEX_SITEMAP_DAYS = settings.WAIT_REINDEX_SITEMAP_DAYS
WAIT_BETWEEN_VALIDATION_SECONDS = settings.WAIT_BETWEEN_VALIDATION_SECONDS

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


@db_periodic_task(crontab(minute="*"))  # La tâche est exécutée chaque minute.
def index_pages():
    max_pending = 600  # On essaye une valeur à la main.
    chunk_size = max(0, max_pending - TrackedPage.objects.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).count())
    now = timezone.now()

    if not has_available_apikey(now):
        print("no more available apikeys for today, skipping execution")
        return

    # Récupérer les pages à indexer
    with transaction.atomic():
        filtered_page_queryset = TrackedPage.objects.filter(
            status=PAGE_STATUS_NEED_INDEXATION,
        ).exclude(site__status=SITE_STATUS_HOLD).order_by(
            F("last_indexation").asc(nulls_first=True)
        )

        if not filtered_page_queryset.exists():
            # Si aucune nouvelle page, essaye de trouver des pages plus anciennes à réindexer
            last_validation_reindex = timezone.now() - datetime.timedelta(days=WAIT_REINDEX_PAGES_DAYS)
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

    # Paralléliser chaque tâche d'indexation
    for page_id in id_page_to_update:
        # Planifie chaque tâche d'indexation de manière asynchrone
        index_page.schedule((page_id,), delay=0)


@db_task(retries=2)  # Cette tâche sera utilisée par Huey et peut être réessayée jusqu'à deux fois
def index_page(page_id):
    end_throttle = time.time() + WAIT_BETWEEN_VALIDATION_SECONDS  # Un délai entre chaque vérification
    retry = False
    with transaction.atomic():
        print("indexing page ", page_id)
        page: TrackedPage = TrackedPage.objects.filter(id=page_id).select_for_update().first()

        if page is None or page.status != PAGE_STATUS_PENDING_INDEXATION_CALL:
            print("page is not marked for indexation. skipping")
            raise CancelExecution(retry=False)

        apikey = get_available_apikey(timezone.now(), APIKEY_USAGE_INDEXATION)
        print("got key", apikey)
        if apikey is None:
            # Page sera vérifiée plus tard
            page.status = PAGE_STATUS_NEED_INDEXATION
            page.save()
            print("no more api key available. no indexation until next availability occurs")
            return

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
            traceback.print_exc()
        else:
            page.status = PAGE_STATUS_INDEXED
            page.last_indexation = timezone.now()
            page.save()
            print("page saved.")

        # Enregistrer une erreur si elle a eu lieu
        if error:
            if apikey and page and page.site and error:
                CallError.objects.create(api_key=apikey, page=page, site=page.site, error=error)
            else:
                logger.error(f"Unable to create CallError: api_key={apikey}, page={page}, site={getattr(page, 'site', None)}, error={error}")

    # Attendre si nécessaire avant la fin de l'exécution pour limiter la fréquence des appels
    remaining = end_throttle - time.time()
    if remaining > 0:
        time.sleep(remaining)

    if retry:
        raise CancelExecution()
