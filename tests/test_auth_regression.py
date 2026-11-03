"""Semantics that must not change."""

from datetime import timedelta

import pytest
from django.utils import timezone

from uw_api_keys.models import APIKeyScope, OperationType

pytestmark = pytest.mark.django_db
URL = "/api/widgets/"


def _scope(api_key, model, *ops):
    from django.contrib.contenttypes.models import ContentType

    scope = APIKeyScope.objects.create(
        api_key=api_key, content_type=ContentType.objects.get_for_model(model)
    )
    scope.operations.add(*OperationType.objects.filter(name__in=ops))
    return scope


def test_should_allow_everything_when_key_has_no_scopes(client, api_key, auth):
    _, key = api_key
    assert client.get(URL, **auth(key)).status_code == 200
    assert (
        client.post(URL, {"name": "w"}, format="json", **auth(key)).status_code == 201
    )


def test_should_allow_operation_granted_by_scope(client, api_key, auth):
    from tests.testapp.models import Widget

    obj, key = api_key
    _scope(obj, Widget, "read")
    assert client.get(URL, **auth(key)).status_code == 200


def test_should_deny_operation_not_granted_by_scope(client, api_key, auth):
    from tests.testapp.models import Widget

    obj, key = api_key
    _scope(obj, Widget, "read")
    response = client.post(URL, {"name": "w"}, format="json", **auth(key))
    assert response.status_code == 403


def test_should_deny_model_without_scope(client, api_key, auth):
    from tests.testapp.models import Widget

    obj, key = api_key
    _scope(obj, Widget, "read")
    assert client.get("/api/gadgets/", **auth(key)).status_code == 403


def test_should_deny_scope_with_no_operations(client, api_key, auth):
    from tests.testapp.models import Widget

    obj, key = api_key
    _scope(obj, Widget)
    assert client.get(URL, **auth(key)).status_code == 403


def test_should_reject_invalid_key_with_401(client, api_key, auth):
    obj, key = api_key
    wrong = key[:-1] + ("a" if key[-1] != "a" else "b")
    assert client.get(URL, **auth(wrong)).status_code == 401


def test_should_reject_expired_key_with_401(client, make_key, auth):
    _, key = make_key(expires_at=timezone.now() - timedelta(minutes=1))
    assert client.get(URL, **auth(key)).status_code == 401


def test_should_reject_origin_not_in_valid_origins(client, make_key, auth):
    _, key = make_key(valid_origins="http://a.example")
    response = client.get(URL, HTTP_ORIGIN="http://evil.example", **auth(key))
    assert response.status_code == 401


def test_should_accept_origin_in_valid_origins(client, make_key, auth):
    _, key = make_key(valid_origins="http://a.example")
    response = client.get(URL, HTTP_ORIGIN="http://a.example", **auth(key))
    assert response.status_code == 200
