from __future__ import annotations

from django.urls import include, path
from onebrain_api import views as api_views
from onebrain_host import health

urlpatterns = [
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),
    path("api/openapi.json", api_views.openapi_json, name="openapi-json"),
    path(
        "api/jobs/graph-aggregation/status",
        api_views.graph_aggregation_job_status,
        name="graph-aggregation-job-status-public",
    ),
    path("", include("onebrain_web.urls")),
]
