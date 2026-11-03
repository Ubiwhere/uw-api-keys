from argparse import ArgumentTypeError
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from uw_api_keys.conf import uw_api_keys_settings
from uw_api_keys.models import APIKeyLogEvent


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise ArgumentTypeError("must be a positive integer")
    return number


class Command(BaseCommand):
    help = "Deletes API key usage log events older than a number of days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=_positive_int,
            help="Delete events older than this many days "
            "(defaults to UW_API_KEYS_LOG_RETENTION_DAYS).",
        )
        parser.add_argument("--batch-size", type=_positive_int, default=10000)

    def handle(self, *args, **options):
        days = options["days"] or uw_api_keys_settings.LOG_RETENTION_DAYS
        if not days:
            raise CommandError(
                "No retention given: pass --days or set UW_API_KEYS_LOG_RETENTION_DAYS."
            )
        cutoff = timezone.now() - timedelta(days=days)
        queryset = APIKeyLogEvent.objects.filter(created_at__lt=cutoff)
        deleted = 0
        while True:
            ids = list(
                queryset.order_by("pk").values_list("pk", flat=True)[
                    : options["batch_size"]
                ]
            )
            if not ids:
                break
            count, _ = APIKeyLogEvent.objects.filter(pk__in=ids).delete()
            deleted += count
        self.stdout.write(
            f"Deleted {deleted} API key log events older than {days} days."
        )
