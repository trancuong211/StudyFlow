from django.core.management.base import BaseCommand

from apps.notifications.tasks import send_due_reminders


class Command(BaseCommand):
    help = "Send due reminders immediately (console email backend by default in development)."

    def handle(self, *args, **options):
        self.stdout.write(f"Created {send_due_reminders()} notifications.")
