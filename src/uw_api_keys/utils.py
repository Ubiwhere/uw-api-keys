"""Module containing utility functions"""

import json

from django.db.models import QuerySet


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
