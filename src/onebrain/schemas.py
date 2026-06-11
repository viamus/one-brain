from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryType = Literal[
    "rule",
    "preference",
    "workflow",
    "skill",
    "decision",
    "pitfall",
    "context",
    "runbook",
    "fact",
    "note",
]

MemoryStatus = Literal["active", "archived", "superseded", "deleted"]


def _normalized_string_list(value: list[str], *, lowercase: bool = True) -> list[str]:
    items = [item.strip() for item in value if item.strip()]
    if lowercase:
        items = [item.lower() for item in items]
    return sorted(set(items))


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
        return _normalized_string_list(value)


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, min_length=1)
    content: str | None = Field(default=None, min_length=1)
    version: str | None = Field(default=None, max_length=64)
    when_to_use: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="skill"))
    entities: list[EntityInput] = Field(default_factory=list)
    relations: list[RelationInput] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return _normalized_string_list(value)

    @field_validator("capabilities", "tools")
    @classmethod
    def normalize_named_lists(cls, value: list[str]) -> list[str]:
        return _normalized_string_list(value, lowercase=False)

    @model_validator(mode="after")
    def require_skill_body(self) -> SkillCreate:
        if not (self.instructions and self.instructions.strip()) and not (
            self.content and self.content.strip()
        ):
            raise ValueError("skill requires instructions or content")
        return self


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


class GraphRequest(BaseModel):
    query: str | None = None
    memory_ids: list[uuid.UUID] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    include_entities: bool = True
    include_relations: bool = True
    include_correlations: bool = True
    include_vector_correlations: bool = True
    correlation_limit: int = Field(default=250, ge=0, le=2000)
    max_correlation_degree: int = Field(default=6, ge=1, le=50)
    vector_neighbors_per_memory: int = Field(default=4, ge=1, le=20)
    vector_similarity_threshold: float = Field(default=0.72, ge=0.0, le=1.0)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class GraphNode(BaseModel):
    id: str
    node_type: str
    label: str
    subtype: str | None = None
    summary: str | None = None
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    edge_type: str
    label: str | None = None
    weight: float = 1.0
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    query: str | None
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    memory_count: int
    entity_count: int
    omitted: int = 0


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
