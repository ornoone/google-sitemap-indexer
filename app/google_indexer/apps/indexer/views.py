from django.contrib.messages.context_processors import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import ListView, DetailView, DeleteView
from django.views.generic.edit import FormMixin, ProcessFormView, ModelFormMixin

from google_indexer.apps.indexer.form import TrackedSiteForm, ApikeyImportForm
from google_indexer.apps.indexer.models import TrackedSite, TrackedPage, ApiKey


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

import json
from django.contrib import messages
class ApiKeyListView(FormMixin, ListView, ProcessFormView):
    model = ApiKey
    form_class = ApikeyImportForm

    def get_success_url(self):
        return reverse('indexer:apikey-list')

    def form_valid(self, form):
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

            ApiKey.objects.create(name=name, content=content)
            messages.success(request, "%s: file imported" % name)

        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        self.object_list = self.get_queryset()
        print(request.FILES)
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class ApiKeyDeleteView(DeleteView):
    model = ApiKey

    def get_success_url(self):
        return reverse('indexer:apikey-list')