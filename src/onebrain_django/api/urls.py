from __future__ import annotations

from django.urls import path

from onebrain_django.api import views

app_name = "onebrain_api"

urlpatterns = [
    path("memories", views.capture_memory, name="capture-memory"),
    path("memories/by-source", views.get_memory_by_source_ref, name="memory-by-source"),
    path("memories/<str:memory_id>", views.get_memory, name="memory-detail"),
    path("skills", views.capture_skill, name="capture-skill"),
    path("skills/search", views.search_skills, name="search-skills"),
    path("ingestion/analyze", views.analyze_ingestion, name="ingestion-analyze"),
    path("ingestion/commit", views.commit_ingestion, name="ingestion-commit"),
    path("search", views.search, name="search"),
    path("graph", views.graph, name="graph"),
    path("context", views.context_pack, name="context-pack"),
    path("correlate", views.correlate, name="correlate"),
]
