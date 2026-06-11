from __future__ import annotations

from django.urls import path

from onebrain_django import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("graph", views.graph_view, name="graph-view"),
    path("graph/data", views.graph_data, name="graph-data"),
    path("v1/memories", views.capture_memory, name="capture-memory"),
    path("v1/memories/by-source", views.get_memory_by_source_ref, name="memory-by-source"),
    path("v1/memories/<str:memory_id>", views.get_memory, name="memory-detail"),
    path("v1/skills", views.capture_skill, name="capture-skill"),
    path("v1/ingestion/analyze", views.analyze_ingestion, name="ingestion-analyze"),
    path("v1/ingestion/commit", views.commit_ingestion, name="ingestion-commit"),
    path("v1/skills/search", views.search_skills, name="search-skills"),
    path("v1/search", views.search, name="search"),
    path("v1/graph", views.graph, name="graph"),
    path("v1/context", views.context_pack, name="context-pack"),
    path("v1/correlate", views.correlate, name="correlate"),
]
