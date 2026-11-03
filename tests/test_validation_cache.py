from datetime import timedelta

import pytest
from django.utils import timezone

from uw_api_keys.models import APIKey

pytestmark = pytest.mark.django_db
URL = "/api/widgets/"


def test_should_verify_hash_once_for_repeated_requests_with_same_key(
    client, api_key, auth, hasher, conf
):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    _, key = api_key
    assert client.get(URL, **auth(key)).status_code == 200
    assert client.get(URL, **auth(key)).status_code == 200
    assert hasher.verify_calls == 1


def test_should_reject_old_key_after_rotation_even_when_cached(
    client, api_key, auth, conf
):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    obj, old_key = api_key
    assert client.get(URL, **auth(old_key)).status_code == 200
    new_key = APIKey.objects.update_key(obj).final_key
    assert client.get(URL, **auth(old_key)).status_code == 401
    assert client.get(URL, **auth(new_key)).status_code == 200


def test_should_reject_key_after_deletion_even_when_cached(client, api_key, auth, conf):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    obj, key = api_key
    assert client.get(URL, **auth(key)).status_code == 200
    obj.delete()
    assert client.get(URL, **auth(key)).status_code == 401


def test_should_reject_key_that_expires_after_being_cached(
    client, make_key, auth, conf
):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    obj, key = make_key(expires_at=timezone.now() + timedelta(hours=1))
    assert client.get(URL, **auth(key)).status_code == 200
    APIKey.objects.filter(pk=obj.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert client.get(URL, **auth(key)).status_code == 401


def test_should_verify_hash_on_every_request_when_cache_disabled(
    client, api_key, auth, hasher, conf
):
    conf(VALIDATION_CACHE_TIMEOUT=0)
    _, key = api_key
    for _ in range(3):
        assert client.get(URL, **auth(key)).status_code == 200
    assert hasher.verify_calls == 3


def test_should_not_cache_failed_validation(client, api_key, auth, hasher, conf):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    _, key = api_key
    wrong = key[:-1] + ("a" if key[-1] != "a" else "b")
    assert client.get(URL, **auth(wrong)).status_code == 401
    assert client.get(URL, **auth(wrong)).status_code == 401
    assert hasher.verify_calls == 2


def test_should_reject_wrong_private_key_for_cached_public_key(
    client, api_key, auth, conf
):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    _, key = api_key
    assert client.get(URL, **auth(key)).status_code == 200
    wrong = key[:-1] + ("a" if key[-1] != "a" else "b")
    assert client.get(URL, **auth(wrong)).status_code == 401


def _cache_entry(key):
    from django.core.cache import caches

    from uw_api_keys.models import _validation_cache_key

    return caches["default"].get(_validation_cache_key(key))


def test_should_evict_cache_entry_of_rotated_key(client, api_key, auth, conf):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    obj, old_key = api_key
    client.get(URL, **auth(old_key))
    assert _cache_entry(old_key) is not None
    APIKey.objects.update_key(obj)
    assert client.get(URL, **auth(old_key)).status_code == 401
    assert _cache_entry(old_key) is None


def test_should_evict_cache_entry_of_deleted_key(client, api_key, auth, conf):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    obj, key = api_key
    client.get(URL, **auth(key))
    assert _cache_entry(key) is not None
    obj.delete()
    assert client.get(URL, **auth(key)).status_code == 401
    assert _cache_entry(key) is None


def test_should_evict_cache_entry_of_expired_key(client, make_key, auth, conf):
    conf(VALIDATION_CACHE_TIMEOUT=60)
    obj, key = make_key(expires_at=timezone.now() + timedelta(hours=1))
    client.get(URL, **auth(key))
    assert _cache_entry(key) is not None
    APIKey.objects.filter(pk=obj.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert client.get(URL, **auth(key)).status_code == 401
    assert _cache_entry(key) is None
