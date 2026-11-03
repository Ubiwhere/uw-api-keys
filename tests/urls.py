from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tests.testapp.views import GadgetViewSet, WidgetViewSet

router = DefaultRouter()
router.register("widgets", WidgetViewSet)
router.register("gadgets", GadgetViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
]
