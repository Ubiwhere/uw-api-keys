import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from tests.hashers import CountingMD5PasswordHasher
from uw_api_keys.conf import uw_api_keys_settings
from uw_api_keys.models import APIKey


@pytest.fixture(autouse=True)
def _clean_state():
    cache.clear()
    CountingMD5PasswordHasher.verify_calls = 0
    yield
    cache.clear()


@pytest.fixture
def conf(settings):
    """Set `UW_API_KEYS_<NAME>` settings for one test.

    appconf copies values onto the Conf class at import time, so the Django
    setting alone is not seen through `uw_api_keys_settings`. The value is set
    on both layers; the instance override is undone on teardown.
    """
    touched = []

    def _set(**values):
        for name, value in values.items():
            setattr(settings, f"UW_API_KEYS_{name}", value)
            object.__setattr__(uw_api_keys_settings, name, value)
            touched.append(name)

    yield _set
    for name in touched:
        try:
            object.__delattr__(uw_api_keys_settings, name)
        except AttributeError:
            pass


@pytest.fixture
def hasher():
    return CountingMD5PasswordHasher


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def make_key(db):
    def _make(name="key", **fields):
        obj = APIKey.objects.create(name=name, **fields)
        container = APIKey.objects.update_key(obj)
        obj.refresh_from_db()
        return obj, container.final_key

    return _make


@pytest.fixture
def api_key(make_key):
    return make_key("main")


@pytest.fixture
def auth():
    def _auth(key):
        return {"HTTP_AUTHORIZATION": f"Api-Key {key}"}

    return _auth


@pytest.fixture
def admin_client(db, client):
    user = get_user_model().objects.create_superuser("admin", "a@b.c", "pw")
    client.force_login(user)
    client.raise_request_exception = False
    return client
