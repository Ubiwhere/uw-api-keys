"""Module containing utility functions"""

import json
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import unquote_plus

from django.db.models import QuerySet

REDACTED = "[REDACTED]"
_URL_META_KEYS = ("QUERY_STRING", "REQUEST_URI", "RAW_URI")


def redact_headers(headers: Mapping[str, Any], names: Iterable[str]) -> dict:
    """Replaces the value of the named headers (case-insensitive) keeping the key."""
    lowered = {name.lower() for name in names}
    return {
        key: REDACTED if key.lower() in lowered else value
        for key, value in headers.items()
    }


def redact_meta(
    meta: Mapping[str, Any], names: Iterable[str], query_param: str
) -> dict:
    """Redacts the META keys equivalent to the named headers, and the value of
    `query_param` inside the URL-carrying META entries."""
    meta_keys = {"HTTP_" + name.upper().replace("-", "_") for name in names}
    result = {}
    for key, value in meta.items():
        if key in meta_keys:
            value = REDACTED
        elif key in _URL_META_KEYS and isinstance(value, str):
            value = _redact_url(key, value, query_param)
        result[key] = value
    return result


def _redact_query(query: str, param: str) -> str:
    """Redacts the value of `param` (compared after URL-decoding the name, as
    Django does) in a query string, keeping the rest untouched."""
    pairs = []
    for pair in query.split("&"):
        name, sep, _ = pair.partition("=")
        if sep and unquote_plus(name) == param:
            pair = f"{name}={REDACTED}"
        pairs.append(pair)
    return "&".join(pairs)


def _redact_url(meta_key: str, value: str, param: str) -> str:
    if meta_key == "QUERY_STRING":
        return _redact_query(value, param)
    base, sep, query = value.partition("?")
    return f"{base}{sep}{_redact_query(query, param)}" if sep else value


def is_jsonable(x) -> bool:
    """Check if a variable is JSON serializable."""
    try:
        json.dumps(x)
        return True
    except (TypeError, OverflowError):
        return False


def get_content_type_queryset() -> QuerySet:
    """Returns a default `ContentType` queryset."""
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.all()


def get_content_type_label(obj) -> str | None:
    """Receives a `ContentType` object and returns a string representation for it."""
    # Get model of content type obj
    model = obj.model_class()
    if not model:
        return None
    return f"[{model._meta.app_config.verbose_name}] {model._meta.verbose_name}"
