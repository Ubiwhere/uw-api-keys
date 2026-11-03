# uw-api-keys
## Highly customisable and dead-simple API keys for Django REST managed in Django Admin.

This package is a small Django package that provides functionality for creating and managing API keys for Django REST framework applications in Django Admin dashboard. 
It allows for machine-to-machine communication and integration with other systems. 
The package includes models for API keys, operations, API key scopes, and API key log events.
It provides both authentication and permission classes for integrating with Django REST.

This package is designed to be highly customizable and allows you to add scopes to API keys. 
Scopes define the permissions and operations that an API key can perform on specific models. 
This flexibility is achieved by leveraging the Django content type framework and the concept of CRUD operations.
With this package, you can create API keys with different scopes based on the desired level of access. 
For example, you can create an API key that has the ability to perform CRUD operations (`read`, `update`, `delete`, `create`) on `ModelX`, while only having `read` access to `ModelY`. 
This level of granularity allows you to precisely control what actions each API key can perform on different models.

## Installation

To install the Django API Key package, follow these steps:

1. Install the package using pip:

```shell
pip install uw-api-keys @ git+https://github.com/Ubiwhere/uw-api-keys.git
```

2. Add `'uw_api_keys'` to your Django project's `INSTALLED_APPS` setting in the `settings.py` file:

```python
INSTALLED_APPS = [
    ...
    'uw_api_keys',
    ...
]
```

3. Add the authentication class and permission class in your `settings.py` file:

```python


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        "uw_api_keys.backends.APIKeyAuthentication",
    ]
    'DEFAULT_PERMISSION_CLASSES': [
        ...
        'uw_api_keys.backends.APIKeyPermissions',
        ...
    ],
}
```

4. Run database migrations:
```shell
python manage.py migrate uw_api_keys
```

5. Navigate to the Django Admin page. You should see the "API Key" page ready for some machine-to-machine integrations.

## Configuration

The Django API Key package offers a range of customizable configuration options. 
These configurations can be set in your project's settings.py file by adding variables in the format `UW_API_KEYS_<VAR_NAME>=<my_value>`. 
By overriding these defaults, you can tailor the package to your specific needs. For a complete list of configurations and their default values, refer to the [configuration file](https://github.com/Ubiwhere/uw-api-keys/blob/main/src/uw_api_keys/conf.py#L7).

Here are a couple of relevant examples based on the provided configuration file:

1. Changing the API key prefix:
```python
# settings.py
UW_API_KEYS_KEY_PREFIX = "myCompany" # This will output API keys in format: myCompany_Bo9hYkRG6tfZUofF3VBen9uIo1FvGuIt_rwkWPaVRCJEoaQVkEJJsKfraElINSiLL
```

2. Disabling logging of API key usage:
```python
# settings.py
UW_API_KEYS_LOG_KEY_USAGE = False # This will not record any key usage activity and will hide the logging model from django admin
```

3. Enabling API key via query parameter:
```python
# settings.py
UW_API_KEYS_ENABLE_QUERY_PARAM_AUTH = True # You can now pass your API key via query param with "?Api-Key=<yourKey>"
```

These are just a few examples of how you can customize the Django API Key package by overriding the configuration variables in your project's settings.py file. 
You can explore the configuration file further to discover other options and modify them according to your requirements.

## Performance and logging settings

| Setting | Default | Purpose |
|---|---|---|
| `UW_API_KEYS_VALIDATION_CACHE_TIMEOUT` | `60` | Seconds a validated key is cached so the (slow) password hash is not re-verified on every request. `0` disables. Rotating or deleting a key invalidates its cache entry immediately; expiry is checked on every request. |
| `UW_API_KEYS_VALIDATION_CACHE_ALIAS` | `"default"` | Django cache alias used for the validation cache. Use a shared cache (Redis, Memcached) with multiple workers. |
| `UW_API_KEYS_LAST_SEEN_UPDATE_INTERVAL` | `300` | Minimum seconds between `last_seen` writes. `0` updates on every request. |
| `UW_API_KEYS_LOG_REDACTED_HEADERS` | `("Authorization", "Proxy-Authorization", "Cookie")` | Headers (and equivalent `META` keys) stored as `[REDACTED]` in usage logs. The API key query parameter is redacted in `META` too. |
| `UW_API_KEYS_LOG_REQUEST_META` | `True` | Store `request.META` in usage logs. Set to `False` to store `NULL`. Note: under `runserver`, `META` contains the whole process environment, which is **not** redacted. |
| `UW_API_KEYS_LOG_RETENTION_DAYS` | `None` | Retention used by `prune_api_key_logs` when `--days` is not given. |

### Pruning usage logs

```bash
python manage.py prune_api_key_logs --days 30 [--batch-size 10000]
```

Deletes log events older than the given number of days, in batches. Schedule it (cron, Celery beat, ...) to keep the log table small.

### Upgrading from earlier versions

`last_seen` is now written with a queryset `update()`, so `pre_save`/`post_save` signals no longer fire for those writes.

Log rows written by earlier versions may contain the API key in `headers`, `meta` and the query string. They are not scrubbed automatically: prune them with the command above and rotate any key that was logged.
