from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, DeleteView
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import FormMixin, ProcessFormView

from google_indexer.apps.indexer.form import TrackedSiteForm
from google_indexer.apps.indexer.models import TrackedSite, TrackedPage, PAGE_STATUS_NEED_INDEXATION, \
    SITE_STATUS_PENDING, PAGE_STATUS_PENDING_INDEXATION_CALL, \
    SITE_STATUS_HOLD, SITE_STATUS_OK
from google_indexer.apps.indexer.tasks import update_sitemap, index_page


class TrackedSiteListView(FormMixin, ListView, ProcessFormView):
    model = TrackedSite
    form_class = TrackedSiteForm
    
    def get_queryset(self):
        # Récupérer le paramètre de tri de la requête
        sort = self.request.GET.get('sort', 'name')  # 'name' est la valeur par défaut si aucun tri n'est défini
        queryset = TrackedSite.objects.all().order_by(sort)

        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Ajouter le nombre de liens dans la file d'attente
        queue_count = TrackedPage.objects.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).count()
        context['queue_count'] = queue_count

        return context

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        self.object_list = self.get_queryset()

        form = self.get_form()
        if form.is_valid():
            self.object = form.save()
            update_sitemap(self.object.id)
            return HttpResponseRedirect( reverse('indexer:site-detail', kwargs={'pk': self.object.pk}))
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
