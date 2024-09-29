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
    SITE_STATUS_PENDING, PAGE_STATUS_CREATED, PAGE_STATUS_PENDING_VERIFICATION, PAGE_STATUS_PENDING_INDEXATION_CALL
from google_indexer.apps.indexer.tasks import update_sitemap, verify_page, index_page


class TrackedSiteListView(FormMixin, ListView, ProcessFormView):
    model = TrackedSite
    form_class = TrackedSiteForm

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

            object.pages.update(status=PAGE_STATUS_CREATED)
            messages.success(self.request, "all %d pages reseted" % object.pages.count())
        elif action == 'reset_pending':
            object.pages.filter(status=PAGE_STATUS_PENDING_VERIFICATION).update(status=PAGE_STATUS_CREATED)
            object.pages.filter(status=PAGE_STATUS_PENDING_INDEXATION_CALL).update(status=PAGE_STATUS_NEED_INDEXATION)
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
        if action == 'verify':

            TrackedPage.objects.filter(pk=object.id).update(next_verification=timezone.now(), status=PAGE_STATUS_PENDING_VERIFICATION)
            try:
                verify_page(object.id)
            except Exception as exception:
                messages.error(self.request, "verification enqueued failed: %s" % exception)
            else:
                messages.success(self.request, "verification enqueued successfully")
        elif action == "index":
            messages.success(self.request, "indexation enqueued successfully")
            TrackedPage.objects.filter(pk=object.id).update(status=PAGE_STATUS_PENDING_VERIFICATION)
            index_page(object.id)
        else:
            messages.error(self.request, "unknown action %s" % action)
        return HttpResponseRedirect(reverse('indexer:site-detail', kwargs={'pk': object.site_id}))
