"""Conditionally registers the `APIKey` model
into django-admin."""

import copy
import json
from typing import Any, Sequence

from django.contrib import admin, messages
from django.db.models import JSONField
from django.http.request import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .conf import uw_api_keys_settings
from .forms import APIKeyScopeForm
from .models import APIKey, APIKeyLogEvent, KeyContainer


def pretiffy_json_for_admin(field: JSONField) -> str:
    """Receives a django json field as parameter and returns an html
    with a prettified json"""
    return format_html(
        "<pre>{data}</pre>",
        data=json.dumps(
            field,
            indent=4,
            sort_keys=True,
            ensure_ascii=False,
        ),
    )


class APIKeyScopeInline(admin.StackedInline):
    """Inline model so the user can add API key scopes inside the `APIKeyAdmin` page."""

    model = APIKey.scopes.through
    form = APIKeyScopeForm
    extra = 0
    verbose_name = _("API Key Scope")
    verbose_name_plural = _(
        "API Key Scopes - Leave empty for granting permission to everything"
    )
    filter_horizontal = ["operations"]


class APIKeyAdmin(admin.ModelAdmin):
    """Admin class for `APIKey`."""

    # Show the prefix as a read-only field showing the prefix
    # configured in settings
    exclude = ["prefix", "revoked", "public_key", "hashed_key"]
    readonly_fields = ["get_prefix"]
    inlines = [APIKeyScopeInline]
    list_display = ["id", "key_str", "has_expired", "last_seen"]

    @admin.display(description=APIKey._meta.get_field("prefix").verbose_name)
    def get_prefix(self, obj):
        """Returns the prefix configured in package settings."""
        return uw_api_keys_settings.KEY_PREFIX

    @admin.display(description=APIKey._meta.verbose_name)
    def key_str(self, obj: APIKey):
        return str(obj)

    @admin.display(description=_("Has expired"))
    def has_expired(self, obj: APIKey):
        if obj.expired:
            return _("Yes")
        return _("No")

    def save_model(self, request: HttpRequest, obj: APIKey, form, change):
        created: bool = not obj.pk
        if not created:
            return super().save_model(request, obj, form, change)
        # First time, get the private key and display it in a django banner
        key: KeyContainer = obj.__class__.objects.update_key(obj)
        message = _(
            "Your API key: '{key}'. "
            "Please store it somewhere safe - "
            "you will not be able to see it again."
        ).format(key=key.final_key)
        messages.add_message(request, messages.WARNING, message)
        return obj

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Any | None = None,
    ) -> list[str] | tuple[Any, ...]:
        """If object already exists, make some fields read-only."""
        readonly_fields: list = super().get_readonly_fields(request, obj)  # type: ignore
        if obj:
            return copy.deepcopy(readonly_fields) + ["name", "last_seen"]
        return readonly_fields

    def get_fields(self, request: HttpRequest, obj: Any | None) -> Sequence:
        """When first creating the key remove the `last_seen` field."""
        fields = super().get_fields(request, obj)
        if not obj and "last_seen" in fields:
            fields = [field for field in fields if field != "last_seen"]
        return fields


class APIKeyLogEventAdmin(admin.ModelAdmin):
    """Registers the `APIKeyLogEvent` into django admin."""

    search_fields = ["api_key"]
    list_display = ["api_key", "endpoint", "created_at"]
    list_filter = ["api_key__public_key"]
    # Exclude JSON fields to include a custom prettified version
    exclude = ["headers", "meta", "body"]
    readonly_fields = ["_pretty_headers", "_pretty_meta", "_pretty_body"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Logs shouldn't be added manually."""
        return False

    def has_change_permission(self, *args, **kwargs) -> bool:
        """Logs shouldn't be manually edited."""
        return False

    @admin.display(description=APIKeyLogEvent._meta.get_field("headers").verbose_name)
    def _pretty_headers(self, obj: APIKeyLogEvent) -> str | None:
        if obj.headers:
            return pretiffy_json_for_admin(obj.headers)
        return None

    @admin.display(description=APIKeyLogEvent._meta.get_field("meta").verbose_name)
    def _pretty_meta(self, obj: APIKeyLogEvent) -> str | None:
        if obj.meta:
            return pretiffy_json_for_admin(obj.meta)
        return None

    @admin.display(description=APIKeyLogEvent._meta.get_field("body").verbose_name)
    def _pretty_body(self, obj: APIKeyLogEvent) -> str | None:
        if obj.body:
            return pretiffy_json_for_admin(obj.body)
        return None


# Perform conditional registering
if uw_api_keys_settings.ADMIN_REGISTER:
    admin.site.register(APIKey, APIKeyAdmin)

if uw_api_keys_settings.LOG_KEY_USAGE:
    admin.site.register(APIKeyLogEvent, APIKeyLogEventAdmin)
