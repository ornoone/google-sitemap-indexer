from django.core.management.base import BaseCommand
from google_indexer.apps.indexer.tasks import reset_keys_function

class Command(BaseCommand):
    help = 'Reset the key usages manually'

    def handle(self, *args, **kwargs):
        reset_keys_function()
        self.stdout.write(self.style.SUCCESS('Successfully reset the key usages'))
