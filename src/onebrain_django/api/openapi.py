from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from onebrain_core.contracts.schemas import (
    ContextPack,
    ContextRequest,
    CorrelationRequest,
    CorrelationResponse,
    GraphRequest,
    GraphResponse,
    IngestionAnalyzeRequest,
    IngestionCommitRequest,
    IngestionCommitResult,
    IngestionPlan,
    MemoryCreate,
    MemoryOut,
    SearchRequest,
    SearchResponse,
    SkillCreate,
)

Schema = dict[str, Any]


def openapi_schema() -> Schema:
    components: dict[str, Schema] = {}

    def schema_ref(model: type[BaseModel]) -> Schema:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, definition in schema.pop("$defs", {}).items():
            components.setdefault(name, definition)
        components[model.__name__] = schema
        return {"$ref": f"#/components/schemas/{model.__name__}"}

    def json_body(model: type[BaseModel]) -> Schema:
        return {
            "required": True,
            "content": {"application/json": {"schema": schema_ref(model)}},
        }

    def json_response(model: type[BaseModel], description: str = "OK") -> Schema:
        return {
            "description": description,
            "content": {"application/json": {"schema": schema_ref(model)}},
        }

    secured = [{"ApiKeyAuth": []}, {"BearerAuth": []}]

    paths: Schema = {
        "/api/v1/memories": {
            "post": {
                "summary": "Capture memory",
                "description": "Stores a hardened OneBrain memory and indexes it for retrieval.",
                "operationId": "captureMemory",
                "tags": ["Memories"],
                "security": secured,
                "requestBody": json_body(MemoryCreate),
                "responses": {
                    "200": json_response(MemoryOut),
                    "401": {"description": "Missing API key"},
                    "403": {"description": "Invalid API key"},
                    "422": {"description": "Validation error"},
                },
            }
        },
        "/api/v1/memories/by-source": {
            "get": {
                "summary": "Get memory by source reference",
                "description": (
                    "Finds the active memory associated with an external source reference."
                ),
                "operationId": "getMemoryBySourceRef",
                "tags": ["Memories"],
                "security": secured,
                "parameters": [
                    {
                        "name": "source_ref",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": json_response(MemoryOut),
                    "400": {"description": "Missing source_ref"},
                    "404": {"description": "Memory not found"},
                },
            }
        },
        "/api/v1/memories/{memory_id}": {
            "get": {
                "summary": "Get memory",
                "description": "Loads one memory by UUID.",
                "operationId": "getMemory",
                "tags": ["Memories"],
                "security": secured,
                "parameters": [
                    {
                        "name": "memory_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "200": json_response(MemoryOut),
                    "400": {"description": "Invalid memory id"},
                    "404": {"description": "Memory not found"},
                },
            }
        },
        "/api/v1/skills": {
            "post": {
                "summary": "Capture skill",
                "description": "Normalizes a skill payload into a OneBrain skill memory.",
                "operationId": "captureSkill",
                "tags": ["Skills"],
                "security": secured,
                "requestBody": json_body(SkillCreate),
                "responses": {
                    "200": json_response(MemoryOut),
                    "401": {"description": "Missing API key"},
                    "403": {"description": "Invalid API key"},
                    "422": {"description": "Validation error"},
                },
            }
        },
        "/api/v1/skills/search": {
            "post": {
                "summary": "Search skills",
                "description": "Runs memory search constrained to skill memories.",
                "operationId": "searchSkills",
                "tags": ["Skills"],
                "security": secured,
                "requestBody": json_body(SearchRequest),
                "responses": {"200": json_response(SearchResponse)},
            }
        },
        "/api/v1/ingestion/analyze": {
            "post": {
                "summary": "Analyze ingestion path",
                "description": "Builds a contextual ingestion plan without committing memories.",
                "operationId": "analyzeIngestion",
                "tags": ["Ingestion"],
                "security": secured,
                "requestBody": json_body(IngestionAnalyzeRequest),
                "responses": {
                    "200": json_response(IngestionPlan),
                    "404": {"description": "Path not found"},
                    "422": {"description": "Validation error"},
                },
            }
        },
        "/api/v1/ingestion/commit": {
            "post": {
                "summary": "Commit ingestion plan",
                "description": "Creates memories from a previously analyzed ingestion plan.",
                "operationId": "commitIngestion",
                "tags": ["Ingestion"],
                "security": secured,
                "requestBody": json_body(IngestionCommitRequest),
                "responses": {"200": json_response(IngestionCommitResult)},
            }
        },
        "/api/v1/search": {
            "post": {
                "summary": "Search memories",
                "description": (
                    "Retrieves memories using semantic search and graph-guided related context."
                ),
                "operationId": "searchMemories",
                "tags": ["Retrieval"],
                "security": secured,
                "requestBody": json_body(SearchRequest),
                "responses": {"200": json_response(SearchResponse)},
            }
        },
        "/api/v1/graph": {
            "get": {
                "summary": "Query memory graph",
                "description": "Builds graph data from query parameters for lightweight clients.",
                "operationId": "queryGraph",
                "tags": ["Graph"],
                "security": secured,
                "parameters": [
                    {"name": "query", "in": "query", "schema": {"type": "string"}},
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                    {"name": "memory_type", "in": "query", "schema": {"type": "string"}},
                    {"name": "tag", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": json_response(GraphResponse)},
            },
            "post": {
                "summary": "Build memory graph",
                "description": (
                    "Builds graph nodes, edges, correlations, and grouping opportunities."
                ),
                "operationId": "buildGraph",
                "tags": ["Graph"],
                "security": secured,
                "requestBody": json_body(GraphRequest),
                "responses": {"200": json_response(GraphResponse)},
            },
        },
        "/api/v1/context": {
            "post": {
                "summary": "Compose context pack",
                "description": (
                    "Returns LLM-ready memories using search, rules, and graph-guided "
                    "related memories."
                ),
                "operationId": "composeContext",
                "tags": ["Retrieval"],
                "security": secured,
                "requestBody": json_body(ContextRequest),
                "responses": {"200": json_response(ContextPack)},
            }
        },
        "/api/v1/correlate": {
            "post": {
                "summary": "Find correlations",
                "description": "Returns deterministic correlations by memory id or query.",
                "operationId": "correlateMemories",
                "tags": ["Graph"],
                "security": secured,
                "requestBody": json_body(CorrelationRequest),
                "responses": {"200": json_response(CorrelationResponse)},
            }
        },
    }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "OneBrain Django API",
            "version": "0.1.0",
            "description": (
                "Corporate Django API for OneBrain memories, skills, graph correlations, "
                "contextual ingestion, and MCP-backed retrieval."
            ),
        },
        "paths": paths,
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                },
            },
            "schemas": components,
        },
    }
