"""Module containing custom django-admin forms."""

from django import forms
from django.utils.module_loading import import_string

from .conf import uw_api_keys_settings
from .models import APIKeyScope, OperationType


class APIKeyScopeForm(forms.ModelForm):
    """Custom form for `APIKeyScope` to customize
    the queryset of `content_type` according to the settings-defined
    queryset."""

    operations = forms.ModelMultipleChoiceField(
        queryset=OperationType.objects.all(),
        widget=forms.CheckboxSelectMultiple(),
        required=True,
    )

    class Meta:
        model = APIKeyScope
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit the queryset to only models of smart cities apps
        # but exclude historical models

        self.fields["content_type"].queryset = import_string(
            uw_api_keys_settings.CONTENT_TYPE_QUERYSET_FN
        )()

        # Set the label for each option to be the model's verbose name
        self.fields["content_type"].label_from_instance = import_string(
            uw_api_keys_settings.CONTENT_TYPE_LABEL_FROM_INSTANCE_FN
        )
