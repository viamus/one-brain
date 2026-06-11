from __future__ import annotations

from django.urls import include, path

from onebrain_django.api import views as api_views
from onebrain_django.web import views as web_views

urlpatterns = [
    path("healthz", web_views.healthz, name="healthz"),
    path("readyz", web_views.readyz, name="readyz"),
    path("api/openapi.json", api_views.openapi_json, name="openapi-json"),
    path("", include("onebrain_django.web.urls")),
    path("api/v1/", include("onebrain_django.api.urls", namespace="onebrain_api")),
    path("v1/", include("onebrain_django.api.urls", namespace="onebrain_legacy_api")),
]
