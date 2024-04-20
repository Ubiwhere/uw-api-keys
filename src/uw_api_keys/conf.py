from appconf import AppConf
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _


class Conf(AppConf):
    """Settings for this package"""

    # Key settings
    KEY_PREFIX: str = "ubiwhere"
    PRIVATE_KEY_LENGTH: int = 32
    LOG_KEY_USAGE: bool = True
    ENABLE_QUERY_PARAM_AUTH: bool = False

    # API settings
    AUTH_HEADER_PREFIX: str = "Api-Key"
    INVALID_API_KEY_ERROR_MSG: str = _("Provided API key is invalid")
    INSUFFICIENT_SCOPES_ERROR_MSG: str = _(
        "Provided API key is valid, but has insufficient scopes"
    )
    INVALID_ORIGIN_ERROR_MSG: str = _(
        "Provided API key is valid, but origin '%s' is not."
    )
    # Labelling
    APP_VERBOSE_NAME: str = _("API Keys")
    API_KEY_FK_VERBOSE_NAME: str = _("API Key")
    CONTENT_TYPE_FK_VERBOSE_NAME: str = _("Entity")
    OPERATION_VERBOSE_NAME: str = _("Operation")
    M2M_MODEL_VERBOSE_NAME: str = _("Entity permission")
    M2M_MODEL_VERBOSE_NAME_PLURAL: str = _("Entity permissions")

    # Admin integration
    ADMIN_REGISTER: bool = True
    CONTENT_TYPE_QUERYSET_FN: str = "uw_api_keys.utils.get_content_type_queryset"
    CONTENT_TYPE_LABEL_FROM_INSTANCE_FN: str = (
        "uw_api_keys.utils.get_content_type_label"
    )

    @staticmethod
    def _validate_callable(setting: str):
        try:
            result = import_string(setting)
            if not callable(result):
                raise ImportError
        except ImportError as err:
            raise ImproperlyConfigured(
                "[uw_api_keys] Setting `CONTENT_TYPE_QUERYSET_FN` does not point"
                " to a valid import function."
            ) from err

    def configure_content_type_queryset_fn(self, value: str):
        """Validate that the configured `CONTENT_TYPE_QUERYSET_FN` points to a valid
        callable."""
        self._validate_callable(value)
        return value

    def configure_content_type_label_from_instance_fn(self, value: str):
        """Validate that the configured `CONTENT_TYPE_LABEL_FROM_INSTANCE_FN`
        points to a valid callable."""
        self._validate_callable(value)
        return value

    class Meta:
        prefix = "UW_API_KEYS"


uw_api_keys_settings = Conf()
