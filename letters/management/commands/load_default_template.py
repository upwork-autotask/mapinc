from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from letters.docgen import TEMPLATE_FIXTURE
from letters.models import AppSettings


class Command(BaseCommand):
    help = "Load the bundled Clinicals Request .docx into Settings > template."

    def handle(self, *args, **options):
        s = AppSettings.load()
        if s.template:
            s.template.delete(save=False)
        s.template.save(TEMPLATE_FIXTURE.name, ContentFile(TEMPLATE_FIXTURE.read_bytes()), save=False)
        s.save()
        self.stdout.write(self.style.SUCCESS(f"Template loaded: {s.template.name}"))
