from django.apps import AppConfig
from django.db.models.signals import post_migrate

from .conf import uw_api_keys_settings


def create_operations(sender, **kwargs):
    """Makes sure the 4 CRUD `Operation` objects exist."""
    from .models import OperationType

    for op in OperationType.OperationChoices:
        OperationType.objects.get_or_create(name=op)


class ApiKeysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "uw_api_keys"
    label = "uw_api_keys"
    verbose_name = uw_api_keys_settings.APP_VERBOSE_NAME

    def ready(self) -> None:
        post_migrate.connect(create_operations, sender=self)
