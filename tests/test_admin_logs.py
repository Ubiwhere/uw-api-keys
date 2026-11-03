import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from uw_api_keys.models import APIKeyLogEvent

pytestmark = pytest.mark.django_db
CHANGELIST = "/admin/uw_api_keys/apikeylogevent/"
LOG_TABLE = "uw_api_keys_apikeylogevent"


def _logs(api_key, n, prefix="e"):
    APIKeyLogEvent.objects.bulk_create(
        [APIKeyLogEvent(api_key=api_key, endpoint=f"/{prefix}{i}") for i in range(n)]
    )


def _log_queries(ctx):
    return [q["sql"] for q in ctx.captured_queries if LOG_TABLE in q["sql"]]


def _analyze():
    with connection.cursor() as cur:
        cur.execute(f"ANALYZE {LOG_TABLE}")


def test_should_not_grow_query_count_with_number_of_rows_shown(admin_client, api_key):
    obj, _ = api_key
    _logs(obj, 3)
    with CaptureQueriesContext(connection) as small:
        assert admin_client.get(CHANGELIST).status_code == 200
    _logs(obj, 10, "more")
    with CaptureQueriesContext(connection) as large:
        assert admin_client.get(CHANGELIST).status_code == 200
    assert len(large) == len(small)


def test_should_not_use_distinct_on_log_table_queries(admin_client, api_key):
    obj, _ = api_key
    _logs(obj, 3)
    with CaptureQueriesContext(connection) as ctx:
        response = admin_client.get(CHANGELIST, {"q": obj.name})
    assert response.status_code == 200
    assert not [s for s in _log_queries(ctx) if "DISTINCT" in s.upper()]


def test_should_search_logs_by_api_key_name(admin_client, make_key):
    first, _ = make_key("alpha-key")
    second, _ = make_key("beta-key")
    _logs(first, 2, "a")
    _logs(second, 3, "b")
    response = admin_client.get(CHANGELIST, {"q": "alpha-key"})
    assert response.status_code == 200
    rows = list(response.context["cl"].result_list)
    assert {r.api_key_id for r in rows} == {first.pk}
    assert len(rows) == 2


def test_should_filter_logs_by_api_key(admin_client, make_key):
    first, _ = make_key("alpha-key")
    second, _ = make_key("beta-key")
    _logs(first, 2, "a")
    _logs(second, 3, "b")
    response = admin_client.get(CHANGELIST, {"api_key__id__exact": first.pk})
    assert response.status_code == 200
    assert response.context["cl"].result_count == 2
    assert "api_key" in [
        getattr(f, "field_path", None) for f in response.context["cl"].filter_specs
    ]


def test_should_not_count_log_table_on_unfiltered_changelist(admin_client, api_key):
    obj, _ = api_key
    _logs(obj, 3)
    _analyze()
    with CaptureQueriesContext(connection) as ctx:
        assert admin_client.get(CHANGELIST).status_code == 200
    counts = [s for s in _log_queries(ctx) if "COUNT(" in s.upper()]
    assert counts == []


def test_should_count_exactly_when_changelist_is_filtered(admin_client, make_key):
    first, _ = make_key("alpha-key")
    second, _ = make_key("beta-key")
    _logs(first, 2, "a")
    _logs(second, 3, "b")
    _analyze()
    response = admin_client.get(CHANGELIST, {"api_key__id__exact": second.pk})
    assert response.status_code == 200
    assert response.context["cl"].result_count == 3
