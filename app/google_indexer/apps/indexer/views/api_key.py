import json

from django.contrib import messages
from django.urls import reverse
from django.views.generic import ListView, DeleteView
from django.views.generic.edit import FormMixin, ProcessFormView

from google_indexer.apps.indexer.form import ApikeyImportForm
from google_indexer.apps.indexer.models import ApiKey, APIKEY_USAGE_INDEXATION


class ApiKeyListView(FormMixin, ListView, ProcessFormView):
    model = ApiKey
    form_class = ApikeyImportForm
    queryset = ApiKey.objects.all().order_by('name')

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
            if form.cleaned_data['usage'] == APIKEY_USAGE_INDEXATION:
                max_per_day = 200
            else:
                max_per_day = 2000
            ApiKey.objects.create(name=name, content=content, usage=form.cleaned_data['usage'], max_per_day=max_per_day)
            messages.success(request, "%s: file imported" % name)

        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        self.object_list = self.get_queryset()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class ApiKeyDeleteView(DeleteView):
    model = ApiKey


    def get_success_url(self):
        return reverse('indexer:apikey-list')
