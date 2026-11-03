import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from tests.testapp.models import Widget
from tests.testapp.views import WidgetViewSet
from uw_api_keys.backends import APIKeyPermissions, APIKeyUser
from uw_api_keys.models import APIKeyScope, OperationType

pytestmark = pytest.mark.django_db


@pytest.fixture
def scoped_key(api_key):
    obj, _ = api_key
    scope = APIKeyScope.objects.create(
        api_key=obj, content_type=ContentType.objects.get_for_model(Widget)
    )
    scope.operations.add(OperationType.objects.get(name="read"))
    return obj


def _request(api_key):
    request = Request(APIRequestFactory().get("/api/widgets/"))
    request.user = APIKeyUser(api_key)
    return request


def test_should_check_scoped_key_permission_with_at_most_one_query(scoped_key):
    ContentType.objects.get_for_model(Widget)
    view = WidgetViewSet()
    with CaptureQueriesContext(connection) as ctx:
        assert APIKeyPermissions().has_permission(_request(scoped_key), view)
    assert len(ctx) <= 1, [q["sql"] for q in ctx.captured_queries]


def test_should_issue_no_queries_for_object_permission_after_permission(scoped_key):
    ContentType.objects.get_for_model(Widget)
    view = WidgetViewSet()
    request = _request(scoped_key)
    perm = APIKeyPermissions()
    assert perm.has_permission(request, view)
    with CaptureQueriesContext(connection) as ctx:
        assert perm.has_object_permission(request, view, Widget())
    assert len(ctx) == 0, [q["sql"] for q in ctx.captured_queries]
