from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from uw_api_keys.models import APIKeyLogEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def logs(api_key):
    obj, _ = api_key
    now = timezone.now()
    ids = {}
    for label, age in [("old1", 40), ("old2", 31), ("old3", 90), ("new", 5)]:
        ev = APIKeyLogEvent.objects.create(api_key=obj, endpoint=label)
        APIKeyLogEvent.objects.filter(pk=ev.pk).update(
            created_at=now - timedelta(days=age)
        )
        ids[label] = ev.pk
    return ids


def _remaining():
    return set(APIKeyLogEvent.objects.values_list("endpoint", flat=True))


def test_should_prune_only_rows_older_than_days_argument(logs):
    out = StringIO()
    call_command("prune_api_key_logs", "--days", "30", stdout=out)
    assert _remaining() == {"new"}
    assert out.getvalue().startswith("Deleted 3 ")


def test_should_prune_in_batches_smaller_than_row_count(logs):
    call_command("prune_api_key_logs", "--days", "30", "--batch-size", "1")
    assert _remaining() == {"new"}


def test_should_use_retention_setting_when_days_not_given(logs, conf):
    conf(LOG_RETENTION_DAYS=60)
    call_command("prune_api_key_logs")
    assert _remaining() == {"old1", "old2", "new"}


def test_should_fail_when_neither_days_nor_setting_given(logs, conf):
    conf(LOG_RETENTION_DAYS=None)
    with pytest.raises(CommandError, match="days"):
        call_command("prune_api_key_logs")
    assert _remaining() == {"old1", "old2", "old3", "new"}


@pytest.mark.parametrize("option", ["--days", "--batch-size"])
@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_should_reject_non_positive_integer_arguments(logs, option, value, capsys):
    args = ["--days", "30", "--batch-size", "10"]
    args[args.index(option) + 1] = value
    with pytest.raises(CommandError, match="must be a positive integer"):
        call_command("prune_api_key_logs", *args)
    assert _remaining() == {"old1", "old2", "old3", "new"}
