from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from uw_api_keys.models import APIKey

pytestmark = pytest.mark.django_db
URL = "/api/widgets/"


def _apikey_updates(ctx):
    return [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("UPDATE")
        and "uw_api_keys_apikey" in q["sql"]
        and "apikeylog" not in q["sql"]
    ]


def test_should_set_last_seen_on_first_use(client, api_key, auth, conf):
    conf(LAST_SEEN_UPDATE_INTERVAL=300)
    obj, key = api_key
    assert obj.last_seen is None
    assert client.get(URL, **auth(key)).status_code == 200
    obj.refresh_from_db()
    assert obj.last_seen is not None


def test_should_not_update_api_key_row_for_second_request_inside_interval(
    client, api_key, auth, conf
):
    conf(LAST_SEEN_UPDATE_INTERVAL=300)
    _, key = api_key
    client.get(URL, **auth(key))
    with CaptureQueriesContext(connection) as ctx:
        assert client.get(URL, **auth(key)).status_code == 200
    assert _apikey_updates(ctx) == []


def test_should_update_last_seen_after_interval_elapsed(client, api_key, auth, conf):
    conf(LAST_SEEN_UPDATE_INTERVAL=300)
    obj, key = api_key
    stale = timezone.now() - timedelta(seconds=301)
    APIKey.objects.filter(pk=obj.pk).update(last_seen=stale)
    assert client.get(URL, **auth(key)).status_code == 200
    obj.refresh_from_db()
    assert obj.last_seen > stale + timedelta(seconds=300)


def test_should_update_last_seen_every_request_when_interval_is_zero(
    client, api_key, auth, conf
):
    conf(LAST_SEEN_UPDATE_INTERVAL=0)
    _, key = api_key
    client.get(URL, **auth(key))
    with CaptureQueriesContext(connection) as ctx:
        client.get(URL, **auth(key))
    assert len(_apikey_updates(ctx)) == 1
