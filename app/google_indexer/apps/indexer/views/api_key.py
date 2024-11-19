from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, DeleteView
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import FormMixin, ProcessFormView
import datetime
from django.conf import settings
from django.db.models import Count, F, Q, ExpressionWrapper, FloatField
import json

from google_indexer.apps.indexer.form import TrackedSiteForm, ApikeyImportForm
from google_indexer.apps.indexer.models import TrackedSite, TrackedPage, PAGE_STATUS_NEED_INDEXATION, \
    SITE_STATUS_PENDING, PAGE_STATUS_PENDING_INDEXATION_CALL, \
    SITE_STATUS_HOLD, SITE_STATUS_OK, PAGE_STATUS_INDEXED, ApiKey, APIKEY_USAGE_INDEXATION
from google_indexer.apps.indexer.tasks import update_sitemap, index_page

WAIT_REINDEX_PAGES_DAYS = settings.WAIT_REINDEX_PAGES_DAYS


class TrackedSiteListView(FormMixin, ListView, ProcessFormView):
    model = TrackedSite
    form_class = TrackedSiteForm
    
    def get_queryset(self):
        # Récupérer le paramètre de tri de la requête
        sort = self.request.GET.get('sort', 'name')  # 'name' est la valeur par défaut si aucun tri n'est défini

        # Annoter le queryset avec les statistiques des pages
        queryset = TrackedSite.objects.annotate(
            total_pages=Count('pages'),
            sending=Count('pages', filter=Q(pages__status=PAGE_STATUS_INDEXED))
        ).order_by(sort)

        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Ajouter le nombre de liens dans la file d'attente
        queue_count = TrackedPage.objects.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).count()
        context['queue_count'] = queue_count
        context['to_index_count'] = TrackedPage.objects.filter(
                status=PAGE_STATUS_NEED_INDEXATION,
            ).exclude(site__status=SITE_STATUS_HOLD).count()
        last_validation_reindex = timezone.now() - datetime.timedelta(days=WAIT_REINDEX_PAGES_DAYS)

        context['to_index_maintenance'] = TrackedPage.objects.filter(
                status=PAGE_STATUS_INDEXED,
                last_indexation__lte=last_validation_reindex
            ).exclude(site__status=SITE_STATUS_HOLD).count()

        # Ajouter le paramètre de tri actuel au contexte pour l'utiliser dans le template
        context['current_sort'] = self.request.GET.get('sort', 'name')

        return context

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = self.get_form()
        if form.is_valid():
            self.object = form.save()
            update_sitemap(self.object.id)
            return HttpResponseRedirect(reverse('indexer:site-detail', kwargs={'pk': self.object.pk}))
        else:
            return self.form_invalid(form)


class ApiKeyListView(FormMixin, ListView, ProcessFormView):
    model = ApiKey
    form_class = ApikeyImportForm
    paginate_by = 100  # définir la pagination à 100 clés par page

    def get_queryset(self):
        # Récupérer le paramètre de tri de la requête
        sort = self.request.GET.get('sort', 'name')  # 'name' est la valeur par défaut si aucun tri n'est défini

        # Annoter le queryset avec le taux d'utilisation des clés
        queryset = ApiKey.objects.annotate(
            usage_rate=ExpressionWrapper(F('count_of_the_day') / F('max_per_day'), output_field=FloatField())
        ).order_by(sort)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ajouter les totaux des utilisations
        usage_counts = ApiKey.total_usage_counts()
        context['total_indexation_keys'] = usage_counts['total_indexation_keys']
        context['total_check_keys'] = usage_counts['total_check_keys']  
        # Ajouter la liste complète des pages pour la pagination
        paginator = context['paginator']
        context['page_numbers'] = range(1, paginator.num_pages + 1)
        # Ajouter le nombre de clés disponibles
        available_keys_count = ApiKey.objects.filter(count_of_the_day__lt=F('max_per_day')).count()
        context['available_keys_count'] = available_keys_count
        # Ajouter le paramètre de tri actuel au contexte pour l'utiliser dans le template
        context['current_sort'] = self.request.GET.get('sort', 'name')
        
        return context

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = self.get_form()
        if form.is_valid():
            request = self.request
            files = form.cleaned_data["file"]
            for f in files:
                name = f.name
                content = f.read()
                try:
                    content = json.loads(content)
                except ValueError:
                    messages.error(request, "%s: file is not a json file" % name)
                    continue
                if ApiKey.objects.filter(name=name).exists() or ApiKey.objects.filter(content=content).exists():
                    messages.error(request, "%s: file already uploaded" % name)
                if form.cleaned_data['usage'] == APIKEY_USAGE_INDEXATION:
                    max_per_day = 200
                else:
                    max_per_day = 2000
                ApiKey.objects.create(name=name, content=content, usage=form.cleaned_data['usage'], max_per_day=max_per_day)
                messages.success(request, "%s: file imported" % name)

            return super().form_valid(form)
        else:
            return self.form_invalid(form)


class TrackedSiteDetailView(DetailView):
    model = TrackedSite
    def get_context_data(self, **kwargs):
        top10 = []
        status_filter = self.request.GET.get('status')
        for status, _ in TrackedPage._meta.get_field("status").flatchoices:
            if status_filter is None or status_filter == status:
                top10.extend(self.object.pages.filter(status=status).order_by('id')[:10])
        return super().get_context_data(top10=top10, **kwargs)



class TrackedSiteDeleteView(DeleteView):
    model = TrackedSite

    def get_success_url(self):
        return reverse('indexer:site-list')


class TrackedSiteActionView(SingleObjectMixin, View):

    model = TrackedSite

    def get(self, request, pk):
        object = self.get_object()
        return HttpResponseRedirect(reverse('indexer:site-detail', kwargs={'pk': object.id}))

    def post(self, request, pk):
        object = self.get_object()
        action = self.request.POST.get('action')
        if action == 'update':
            messages.success(self.request, "update fo sitemap enqueued successfully")
            TrackedSite.objects.filter(pk=object.id).update(status=SITE_STATUS_PENDING)
            update_sitemap(object.id)
        elif action == 'reset_pages':

            object.pages.update(status=PAGE_STATUS_NEED_INDEXATION)
            messages.success(self.request, "all %d pages reseted" % object.pages.count())
        elif action == 'reset_pending':
            object.pages.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).update(status=PAGE_STATUS_NEED_INDEXATION)
        elif action == 'hold':
            object.status = SITE_STATUS_HOLD
            object.save()
        elif action == 'unhold':
            if object.status == SITE_STATUS_HOLD:
                object.status = SITE_STATUS_OK
                object.save()
        else:
            messages.error(self.request, "unknown action %s" % action)
        return HttpResponseRedirect(reverse('indexer:site-detail', kwargs={'pk': object.id}))


class TrackedPageActionView(SingleObjectMixin, View):

    model = TrackedPage

    def get(self, request, pk):
        object = self.get_object()
        return HttpResponseRedirect(reverse('indexer:site-detail', kwargs={'pk': object.site_id}))

    def post(self, request, pk):
        object = self.get_object()
        action = self.request.POST.get('action')
        if action == "index":
            messages.success(self.request, "indexation enqueued successfully")
            TrackedPage.objects.filter(pk=object.id).update(status=PAGE_STATUS_PENDING_INDEXATION_CALL)
            index_page(object.id)
        else:
            messages.error(self.request, "unknown action %s" % action)
        return HttpResponseRedirect(reverse('indexer:site-detail', kwargs={'pk': object.site_id}))
