"""Module containing the API permission class."""

import json

from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest
from rest_framework import exceptions, permissions
from rest_framework.authentication import TokenAuthentication

from .conf import uw_api_keys_settings
from .models import APIKey, APIKeyLogEvent, APIKeyManager, OperationType


class APIKeyUser(AnonymousUser):
    """
    Extension of `AnonymousUser` class:
    - Adds the `api_key` parameter to the `AnonymousUser` instance.

    Based on: https://already-late.medium.com/non-user-authentication-in-django-and-django-rest-framework-drf-febaa23e0c49 # noqa: E501
    """

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    @property
    def is_authenticated(self):
        return True


class APIKeyAuthentication(TokenAuthentication):
    """This authentication backend validates if a provided api key
    in valid or not."""

    keyword = uw_api_keys_settings.AUTH_HEADER_PREFIX
    request: HttpRequest

    def authenticate(self, request: HttpRequest):
        """Override to save incoming request so it can later be accessed in
        `authenticate_credentials` method."""
        self.request = request
        # Check if API key is provided in query param
        if uw_api_keys_settings.ENABLE_QUERY_PARAM_AUTH:
            key = request.GET.get(uw_api_keys_settings.AUTH_HEADER_PREFIX, None)
            if key:
                return self.authenticate_credentials(key)

        # Authenticate with Authorization header as normally
        return super().authenticate(request)

    def authenticate_credentials(self, key: str):
        """Validates the incoming API `key`."""

        key_instance: APIKey | None = APIKeyManager().get_key(key)
        if not key_instance:
            raise exceptions.AuthenticationFailed(
                uw_api_keys_settings.INVALID_API_KEY_ERROR_MSG
            )

        # Log the usage (if configured as such)
        if uw_api_keys_settings.LOG_KEY_USAGE:
            try:
                body = json.loads(self.request.body)
            except json.JSONDecodeError:
                body = self.request.body.decode(errors="ignore")

            APIKeyLogEvent.objects.create(
                api_key=key_instance,
                endpoint=self.request.path,
                operation=OPERATION_MAPPING[self.request.method],  # type:ignore
                headers=dict(self.request.headers),
                meta=dict(self.request.META),
                body=body,
            )

        return (APIKeyUser(key_instance), key)


# Map HTTP methods to CRUD operations
OPERATION_MAPPING: dict[str, str] = {
    "GET": OperationType.OperationChoices.READ,
    "OPTIONS": OperationType.OperationChoices.READ,
    "HEAD": OperationType.OperationChoices.READ,
    "POST": OperationType.OperationChoices.CREATE,
    "PUT": OperationType.OperationChoices.UPDATE,
    "PATCH": OperationType.OperationChoices.UPDATE,
    "DELETE": OperationType.OperationChoices.DELETE,
}


class APIKeyPermissions(permissions.BasePermission):
    """Given a valid `APIKey` instance, it check if the api key
    scopes are sufficient to read the current model."""

    message: str

    @staticmethod
    def _validate_request_user(request) -> APIKey | None:
        """Makes sure the request user is from type `APIKeyUser`.
        If so it returns the underlying `APIKey` instance. Otherwise,
        `None` is returned."""
        user = getattr(request, "user")
        if not isinstance(user, APIKeyUser):
            return None
        return user.api_key

    def _queryset(self, view):
        """Stolen for `rest_framework.permissions.ModelPermissions`."""
        assert (
            hasattr(view, "get_queryset") or getattr(view, "queryset", None) is not None
        ), (
            "Cannot apply {} on a view that does not set "
            "`.queryset` or have a `.get_queryset()` method."
        ).format(
            self.__class__.__name__
        )

        if hasattr(view, "get_queryset"):
            queryset = view.get_queryset()
            assert queryset is not None, "{}.get_queryset() returned None".format(
                view.__class__.__name__
            )
            return queryset
        return view.queryset

    def has_permission(self, request: HttpRequest, view) -> bool:
        """Checks if the current API key has sufficient scopes to access the current
        model."""
        queryset = self._queryset(view)
        model = queryset.model
        current_operation = OPERATION_MAPPING[request.method]  # type:ignore
        api_key = self._validate_request_user(request)

        if not api_key:
            return False

        # Check if key contains the required scope based on the current operation
        # and model
        if api_key.scopes.count() == 0:
            return True

        scopes = api_key.scopes.filter(
            apikeyscope__operations__name=current_operation,
            apikeyscope__content_type=ContentType.objects.get_for_model(model),
        )
        allowed = scopes.exists()
        if not allowed:
            self.message = uw_api_keys_settings.INSUFFICIENT_SCOPES_ERROR_MSG
        return allowed

    def has_object_permission(self, request, view, obj):
        """Delegate to normal permission method, since API keys
        do not contain object level permissions."""
        return self.has_permission(request, view)
