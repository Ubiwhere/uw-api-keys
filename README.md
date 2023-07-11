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

3. Add the authentication backend and permission class in your `settings.py` file:

```python
AUTHENTICATION_BACKENDS = [
    ...
    'uw_api_keys.backends.APIKeyAuthentication',
    ...
]

REST_FRAMEWORK = {
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

5. Navigate to the Django Admin page. You should see the "API Key" page ready for some machine2machine integrations.

## Configuration

The Django API Key package offers a range of customizable configuration options. 
These configurations can be set in your project's settings.py file by adding variables in the format `UW_API_KEYS_<VAR_NAME>=<my_value>`. 
By overriding these defaults, you can tailor the package to your specific needs. For a complete list of configurations and their default values, refer to the [configuration file](https://github.com/Ubiwhere/uw-api-keys/src/uw_api_keys/conf.py).

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

These are just a few examples of how you can customize the Django API Key package by overriding the configuration variables in your project's settings.py file. 
You can explore the configuration file further to discover other options and modify them according to your requirements.