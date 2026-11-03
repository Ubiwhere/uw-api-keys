import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.contenttypes.models import ContentType
from django.core.cache import caches
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from .conf import uw_api_keys_settings

KEY_PART_DELIMITER = "_"
_CACHE_KEY_TEMPLATE = "uw_api_keys:v1:{digest}"


def _validation_cache_key(key: str) -> str:
    return _CACHE_KEY_TEMPLATE.format(digest=hashlib.sha256(key.encode()).hexdigest())


@dataclass
class KeyContainer:
    """API Key data container"""

    key_prefix: str
    public_key: str
    private_key: str
    hashed_key: str

    @property
    def final_key(self):
        """Returns the final API key that should be returned to the user.
        The different key parts are divided by "_" """
        return f"{self.key_prefix}{KEY_PART_DELIMITER}{self.public_key}{KEY_PART_DELIMITER}{self.private_key}"


def make_key() -> KeyContainer:
    """Generates a random API Key"""
    # Generate a random string for the initial key start - "public" part
    public_key = get_random_string(APIKey._meta.get_field("public_key").max_length)
    private_key = get_random_string(uw_api_keys_settings.PRIVATE_KEY_LENGTH)

    return KeyContainer(
        key_prefix=uw_api_keys_settings.KEY_PREFIX,
        public_key=public_key,
        private_key=private_key,
        hashed_key=make_password(private_key),
    )


class APIKeyManager(models.Manager):
    """Custom manager for API Keys."""

    def update_key(self, obj: "APIKey") -> KeyContainer:
        """Given an `APIKey` object it creates a random `public_key``
        and `private_key`, returning a `KeyContainer` dataclass."""
        key: KeyContainer = make_key()
        obj.prefix = key.key_prefix
        obj.public_key = key.public_key
        obj.hashed_key = key.hashed_key
        # Do not store the "private_key"
        obj.save()
        return key

    def get_key(self, key: str) -> Optional["APIKey"]:
        """Returns a `APIKey` object if the provided key string
        is valid. Otherwise, None is returned."""
        try:
            prefix_key, public_key, private_key = key.split(KEY_PART_DELIMITER)
        except ValueError:
            return None

        cached = self._get_cached(key, prefix_key, public_key)
        if cached is not None:
            cached.update_last_seen()
            return cached

        try:
            api_key: APIKey = APIKey.objects.get(
                prefix=prefix_key, public_key=public_key
            )
        except ObjectDoesNotExist:
            return None

        # Check if key is expired
        if api_key.expired:
            return None
        # We got the key by prefix and public key but we need to validate that the
        # private key matches the stored hashed version
        if api_key.is_valid(private_key):
            self._set_cached(key, api_key)
            api_key.update_last_seen()
            return api_key
        return None

    @staticmethod
    def _get_cached(key: str, prefix: str, public_key: str) -> Optional["APIKey"]:
        """Returns the `APIKey` for a previously validated `key`, only if the stored
        row still matches what was validated (so rotation/deletion self-invalidate)."""
        if uw_api_keys_settings.VALIDATION_CACHE_TIMEOUT <= 0:
            return None
        cache = caches[uw_api_keys_settings.VALIDATION_CACHE_ALIAS]
        cache_key = _validation_cache_key(key)
        entry = cache.get(cache_key)
        if not entry:
            return None
        api_key = APIKey.objects.filter(pk=entry["pk"]).first()
        if (
            api_key is None
            or (api_key.prefix, api_key.public_key, api_key.hashed_key)
            != (prefix, public_key, entry["hashed_key"])
            or api_key.expired
        ):
            cache.delete(cache_key)
            return None
        return api_key

    @staticmethod
    def _set_cached(key: str, api_key: "APIKey") -> None:
        timeout = uw_api_keys_settings.VALIDATION_CACHE_TIMEOUT
        if timeout <= 0:
            return
        caches[uw_api_keys_settings.VALIDATION_CACHE_ALIAS].set(
            _validation_cache_key(key),
            {"pk": api_key.pk, "hashed_key": api_key.hashed_key},
            timeout,
        )


class APIKey(models.Model):
    """Represents an API Key that can be created for machine2machine communication
    and integration with other systems."""

    objects = APIKeyManager()

    name = models.CharField(
        verbose_name=_("API Key name"),
        max_length=50,
        blank=False,
        null=False,
        help_text=_("A name that helps you identify this key"),
    )
    prefix = models.CharField(
        max_length=10,
        verbose_name=_("API Key prefix"),
        null=False,
        blank=False,
    )
    public_key = models.CharField(
        max_length=32,
        verbose_name=_("Public key"),
        null=False,
        blank=False,
        unique=True,
    )
    hashed_key = models.CharField(
        max_length=255,
        verbose_name=_("Hashed private key"),
        null=False,
        blank=False,
    )

    expires_at = models.DateTimeField(
        verbose_name=_("Time at which the API Key expires"),
        null=True,
        blank=True,
        help_text=_("Leave as empty for a non-expiring key."),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("Creation time"),
    )
    last_seen = models.DateTimeField(
        null=True,
        verbose_name=_("When the API key was last used"),
    )
    # Scopes of this key
    scopes = models.ManyToManyField(
        ContentType,
        through="APIKeyScope",
        through_fields=("api_key", "content_type"),
        verbose_name=_("Scopes"),
        help_text=_(
            "The scopes that this key can access. "
            "Leave as empty to grant access to everything."
        ),
    )

    # Optional valid origins
    valid_origins = models.TextField(
        verbose_name=_("Valid web origins"),
        null=True,
        blank=True,
        help_text=_(
            "A list of valid web origins for this key. Leave empty to allow all. "
            "Provide one per-line separated by commas.<br/> <b>Example:</b> <br/>"
            "http://localhost:5000,<br/>"
            "https://mydomain.com"
        ),
    )

    # Option to disable usage logging
    # on a per-key basis
    log_usage = models.BooleanField(
        verbose_name=_("Log usage"),
        default=None,
        null=True,
        help_text=format_lazy(
            _(
                "Whether to log usage of this key. This overrides the global setting ({enabled})."
            ),
            enabled=(
                _("Enabled") if uw_api_keys_settings.LOG_KEY_USAGE else _("Not enabled")
            ),
        ),
    )

    def __str__(self) -> str:
        key_hash_str = "*" * 5
        return f"{self.name} - {self.prefix}{KEY_PART_DELIMITER}{self.public_key}{KEY_PART_DELIMITER}{key_hash_str}"

    @property
    def web_origins(self) -> list[str] | None:
        """Return the parsed allowed origins"""
        return (
            [s.strip() for s in self.valid_origins.split(",")]
            if self.valid_origins
            else None
        )

    @property
    def should_log_usage(self) -> bool:
        """Checks if api key usage should be logged. If
        `log_usage` is None, defaults to the global setting `LOG_KEY_USAGE`."""
        if self.log_usage is not None:
            return self.log_usage

        return uw_api_keys_settings.LOG_KEY_USAGE

    class Meta:
        verbose_name = _("API Key")
        verbose_name_plural = _("API Keys")
        ordering = ["-created_at"]

    @property
    def expired(self) -> bool:
        """Returns a boolean indicating if the API key is expired based on `expires_at`
        date field."""
        if self.expires_at is None:
            return False
        return self.expires_at < timezone.now()

    def update_last_seen(self) -> None:
        """Updates the `last_seen` field to the current time, at most once per
        `LAST_SEEN_UPDATE_INTERVAL` seconds."""
        now = timezone.now()
        interval = uw_api_keys_settings.LAST_SEEN_UPDATE_INTERVAL
        if (
            interval > 0
            and self.last_seen is not None
            and now - self.last_seen < timedelta(seconds=interval)
        ):
            return
        APIKey.objects.filter(pk=self.pk).update(last_seen=now)
        self.last_seen = now

    def scope_grants(self) -> frozenset[tuple[int, str | None]]:
        """Returns `(content_type_id, operation name)` pairs for this key's scopes,
        fetched with one query and memoised on the instance. A scope without
        operations yields `(content_type_id, None)`: the key is scoped but grants
        nothing."""
        if not hasattr(self, "_scope_grants"):
            self._scope_grants = frozenset(
                APIKeyScope.objects.filter(api_key=self).values_list(
                    "content_type_id", "operations__name"
                )
            )
        return self._scope_grants

    def is_valid(self, private_key: str) -> bool:
        """Given a private key it checks if it is valid
        using the stored hashed key."""
        return check_password(private_key, self.hashed_key)


class OperationType(models.Model):
    """Defines the possible CRUD operations"""

    class OperationChoices(models.TextChoices):
        READ = "read", _("read")
        CREATE = "create", _("create")
        UPDATE = "update", _("update")
        DELETE = "delete", _("delete")

    name = models.CharField(
        verbose_name=_("Operation"),
        null=False,
        blank=False,
        unique=True,
        choices=OperationChoices.choices,
        max_length=10,
    )

    def __str__(self) -> str:
        return self.get_name_display()  # type:ignore

    class Meta:
        verbose_name = _("Operation")
        verbose_name_plural = _("Operations")


class APIKeyScope(models.Model):
    """Intermediate model between `APIKey` and django's `ContentType`."""

    api_key = models.ForeignKey(
        APIKey,
        verbose_name=uw_api_keys_settings.API_KEY_FK_VERBOSE_NAME,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    content_type = models.ForeignKey(
        ContentType,
        verbose_name=uw_api_keys_settings.CONTENT_TYPE_FK_VERBOSE_NAME,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    operations = models.ManyToManyField(
        to=OperationType,
        verbose_name=uw_api_keys_settings.OPERATION_VERBOSE_NAME,
    )

    def __str__(self) -> str:
        return str(self.api_key) + "-" + str(self.content_type)

    class Meta:
        verbose_name = uw_api_keys_settings.M2M_MODEL_VERBOSE_NAME
        verbose_name_plural = uw_api_keys_settings.M2M_MODEL_VERBOSE_NAME_PLURAL


class APIKeyLogEvent(models.Model):
    """Logs an API key usage."""

    api_key = models.ForeignKey(
        APIKey,
        on_delete=models.CASCADE,
        null=True,
        blank=False,
        verbose_name=APIKey._meta.verbose_name,
        db_index=True,
    )
    endpoint = models.CharField(
        _("Endpoint"),
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )
    # No need for foreign key here
    operation = models.CharField(
        null=True,
        blank=False,
        max_length=10,
        verbose_name=OperationType._meta.verbose_name,
        choices=OperationType.OperationChoices.choices,
    )
    headers = models.JSONField(
        _("Request headers"),
        null=True,
        blank=True,
    )
    meta = models.JSONField(
        _("Request meta-information"),
        null=True,
        blank=True,
    )
    body = models.JSONField(
        _("Request's body"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        verbose_name=_("Log time"),
        auto_now_add=True,
        db_index=True,
    )

    def __str__(self) -> str:
        return f"{str(self.api_key)} - {self.created_at}"

    class Meta:
        verbose_name = _("API Key Log Event")
        verbose_name_plural = _("API Key Log Events")
