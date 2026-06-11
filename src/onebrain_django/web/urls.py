from __future__ import annotations

from django.urls import path

from onebrain_django.web import views

app_name = "onebrain_web"

urlpatterns = [
    path("graph", views.graph_view, name="graph-view"),
    path("graph/data", views.graph_data, name="graph-data"),
]
