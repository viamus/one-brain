from __future__ import annotations

from django.urls import include, path

from onebrain.interfaces.api import views
from onebrain.platform import health

urlpatterns = [
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),
    path("api/openapi.json", views.openapi_json, name="openapi-json"),
    path(
        "api/jobs/graph-aggregation/status",
        views.graph_aggregation_job_status,
        name="graph-aggregation-job-status-public",
    ),
    path("api/v1/", include("onebrain.interfaces.api.urls", namespace="onebrain_api")),
    path("v1/", include("onebrain.interfaces.api.urls", namespace="onebrain_legacy_api")),
]
