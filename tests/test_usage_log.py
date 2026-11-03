import json

import pytest

from uw_api_keys.models import APIKeyLogEvent

pytestmark = pytest.mark.django_db
URL = "/api/widgets/"


def _row_text(event):
    return json.dumps(
        [event.headers, event.meta, event.body, event.endpoint], default=str
    )


@pytest.mark.parametrize("log_meta", [True, False])
def test_should_not_store_api_key_in_usage_log(client, api_key, auth, conf, log_meta):
    conf(LOG_REQUEST_META=log_meta)
    _, key = api_key
    assert client.get(URL, **auth(key)).status_code == 200
    text = _row_text(APIKeyLogEvent.objects.get())
    private_key = key.split("_")[-1]
    assert private_key not in text
    assert key not in text


def test_should_not_store_api_key_from_query_param_in_usage_log(client, api_key, conf):
    conf(ENABLE_QUERY_PARAM_AUTH=True, LOG_REQUEST_META=True)
    _, key = api_key
    assert client.get(f"{URL}?Api-Key={key}").status_code == 200
    text = _row_text(APIKeyLogEvent.objects.get())
    assert key.split("_")[-1] not in text
    assert key not in text


def test_should_redact_cookie_header_in_usage_log(client, api_key, auth):
    _, key = api_key
    client.get(URL, HTTP_COOKIE="sessionid=topsecret", **auth(key))
    event = APIKeyLogEvent.objects.get()
    cookie = {k.lower(): v for k, v in event.headers.items()}["cookie"]
    assert cookie == "[REDACTED]"


def test_should_redact_authorization_header_but_keep_the_header_name(
    client, api_key, auth
):
    _, key = api_key
    client.get(URL, **auth(key))
    event = APIKeyLogEvent.objects.get()
    value = {k.lower(): v for k, v in event.headers.items()}.get("authorization")
    assert value == "[REDACTED]"


def test_should_store_null_meta_when_log_request_meta_disabled(
    client, api_key, auth, conf
):
    conf(LOG_REQUEST_META=False)
    _, key = api_key
    client.get(URL, **auth(key))
    assert APIKeyLogEvent.objects.get().meta is None


def test_should_store_redacted_meta_by_default(client, api_key, auth):
    _, key = api_key
    client.get(URL, **auth(key))
    meta = APIKeyLogEvent.objects.get().meta
    assert meta["HTTP_AUTHORIZATION"] == "[REDACTED]"


def test_should_redact_custom_header_from_setting(client, api_key, auth, conf):
    conf(LOG_REDACTED_HEADERS=["X-Secret"])
    _, key = api_key
    client.get(URL, HTTP_X_SECRET="hunter2", **auth(key))
    event = APIKeyLogEvent.objects.get()
    assert event.headers["X-Secret"] == "[REDACTED]"
    assert event.meta["HTTP_X_SECRET"] == "[REDACTED]"


def test_should_store_meta_when_log_request_meta_enabled(client, api_key, auth, conf):
    conf(LOG_REQUEST_META=True)
    _, key = api_key
    client.get(URL, **auth(key))
    meta = APIKeyLogEvent.objects.get().meta
    assert meta is not None and meta["REQUEST_METHOD"] == "GET"


def test_should_not_store_api_key_from_url_encoded_query_param_name(
    client, api_key, conf
):
    conf(ENABLE_QUERY_PARAM_AUTH=True, LOG_REQUEST_META=True)
    _, key = api_key
    assert client.get(f"{URL}?Api%2DKey={key}&x=1").status_code == 200
    event = APIKeyLogEvent.objects.get()
    assert key.split("_")[-1] not in _row_text(event)
    assert event.meta["QUERY_STRING"].endswith("&x=1")
