"""Remove expired mobile sessions and their encrypted provider logout material."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import MobileAuthSession


class Command(BaseCommand):
    """Run alongside Simple JWT's flushexpiredtokens command."""

    help = "Delete expired mobile authentication sessions."

    def handle(self, *args, **options):
        """Tokens cannot outlive these sessions; revocation records remain until expiry."""
        deleted, _ = MobileAuthSession.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()
        self.stdout.write(f"Deleted {deleted} expired mobile authentication sessions.")
