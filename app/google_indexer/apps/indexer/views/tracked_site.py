from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic import ListView, DetailView, DeleteView
from django.views.generic.edit import FormMixin, ProcessFormView

from google_indexer.apps.indexer.form import TrackedSiteForm
from google_indexer.apps.indexer.models import TrackedSite, TrackedPage


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
            return HttpResponseRedirect( reverse('indexer:site-detail', kwargs={'pk': self.object.pk}))
        else:
            return self.form_invalid(form)



class TrackedSiteDetailView(DetailView):
    model = TrackedSite
    def get_context_data(self, **kwargs):
        top10 = []
        for status, _ in TrackedPage._meta.get_field("status").flatchoices:
            top10.extend(self.object.pages.filter(status=status).order_by('id')[:10])
        return super().get_context_data(top10=top10, **kwargs)




class TrackedSiteDeleteView(DeleteView):
    model = TrackedSite

    def get_success_url(self):
        return reverse('indexer:site-list')


