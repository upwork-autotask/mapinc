from django.core.management.base import BaseCommand

from letters.models import Handoff


class Command(BaseCommand):
    help = "Delete expired handoff tokens (run nightly from Task Scheduler)."

    def handle(self, *args, **options):
        self.stdout.write(f"Purged {Handoff.purge_expired()} expired handoff token(s).")
