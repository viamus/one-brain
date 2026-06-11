from __future__ import annotations

from django.urls import path

from onebrain_web import views

app_name = "onebrain_web"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("graph", views.graph_view, name="graph-view"),
    path("graph/data", views.graph_data, name="graph-data"),
]
