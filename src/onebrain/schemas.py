from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MemoryType = Literal[
    "rule",
    "preference",
    "workflow",
    "decision",
    "pitfall",
    "context",
    "runbook",
    "fact",
    "note",
]

MemoryStatus = Literal["active", "archived", "superseded", "deleted"]


class SourceRef(BaseModel):
    source_type: str = Field(min_length=1, max_length=64)
    source_ref: str | None = None


class EntityInput(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    entity_type: str = Field(default="concept", min_length=1, max_length=64)
    role: str = Field(default="mentioned", min_length=1, max_length=64)
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationInput(BaseModel):
    from_entity: EntityInput
    to_entity: EntityInput
    relation_type: str = Field(min_length=1, max_length=96)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryCreate(BaseModel):
    memory_type: MemoryType = "note"
    title: str | None = Field(default=None, max_length=240)
    content: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="manual"))
    entities: list[EntityInput] = Field(default_factory=list)
    relations: list[RelationInput] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return sorted({tag.strip().lower() for tag in value if tag.strip()})


class MemoryPatch(BaseModel):
    status: MemoryStatus | None = None
    title: str | None = Field(default=None, max_length=240)
    tags: list[str] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    memory_type: str
    status: str
    title: str | None
    content: str
    scope: dict[str, Any]
    tags: list[str]
    confidence: float
    source_type: str
    source_ref: str | None
    valid_from: datetime | None
    valid_to: datetime | None
    supersedes_id: uuid.UUID | None
    metadata: dict[str, Any] = Field(alias="metadata_")
    vector_status: str
    vector_error: str | None
    created_at: datetime
    updated_at: datetime


class SearchFilters(BaseModel):
    memory_types: list[MemoryType] | None = None
    tags: list[str] | None = None
    scope: dict[str, Any] | None = None
    statuses: list[MemoryStatus] = Field(default_factory=lambda: ["active"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    include_graph: bool = True


class SearchHit(BaseModel):
    memory: MemoryOut
    score: float
    reasons: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class ContextRequest(BaseModel):
    task: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    max_tokens: int = Field(default=2000, ge=256, le=32000)
    include_rules: bool = True
    include_related: bool = True
    filters: SearchFilters = Field(default_factory=SearchFilters)


class ContextMemory(BaseModel):
    id: uuid.UUID
    memory_type: str
    title: str | None
    content: str
    tags: list[str]
    scope: dict[str, Any]
    confidence: float
    score: float
    reasons: list[str]


class ContextPack(BaseModel):
    task: str
    token_budget: int
    estimated_tokens: int
    rules: list[ContextMemory]
    memories: list[ContextMemory]
    related: list[ContextMemory]
    omitted: int


class CorrelationRequest(BaseModel):
    memory_id: uuid.UUID | None = None
    query: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=50)


class CorrelationHit(BaseModel):
    memory_id: uuid.UUID
    related_memory_id: uuid.UUID
    score: float
    reasons: list[str]


class CorrelationResponse(BaseModel):
    correlations: list[CorrelationHit]
