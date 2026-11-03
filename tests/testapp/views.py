from rest_framework import serializers, viewsets
from rest_framework.renderers import JSONRenderer

from uw_api_keys.backends import APIKeyAuthentication, APIKeyPermissions

from .models import Gadget, Widget


class _Base(viewsets.ModelViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermissions]
    renderer_classes = [JSONRenderer]


class WidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Widget
        fields = ["id", "name"]


class GadgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gadget
        fields = ["id", "name"]


class WidgetViewSet(_Base):
    queryset = Widget.objects.all()
    serializer_class = WidgetSerializer


class GadgetViewSet(_Base):
    queryset = Gadget.objects.all()
    serializer_class = GadgetSerializer
