from django.apps import AppConfig


class IndexerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'google_indexer.apps.indexer'

    def ready(self):
        import google_indexer.apps.indexer.admin
        # import google_indexer.apps.indexer.templatetags.indexer
