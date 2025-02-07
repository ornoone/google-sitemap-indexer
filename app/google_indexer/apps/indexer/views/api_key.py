import json

from django.contrib import messages
from django.urls import reverse
from django.views.generic import ListView, DeleteView
from django.views.generic.edit import FormMixin, ProcessFormView
from django.db.models import F

from google_indexer.apps.indexer.form import ApikeyImportForm
from google_indexer.apps.indexer.models import ApiKey, APIKEY_USAGE_INDEXATION


class ApiKeyListView(FormMixin, ListView, ProcessFormView):
    model = ApiKey
    form_class = ApikeyImportForm
    queryset = ApiKey.objects.all().order_by('name')
    paginate_by = 100

    def get_queryset(self):
        queryset = super().get_queryset()
        sort = self.request.GET.get('sort', 'name')
        
        # Gérez l'ordre de tri en vérifiant s'il commence par un '-'
        if sort.startswith('-'):
            return queryset.order_by(sort)
        else:
            return queryset.order_by(sort)

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
        
        return context


class ApiKeyDeleteView(DeleteView):
    model = ApiKey


    def get_success_url(self):
        return reverse('indexer:apikey-list')
