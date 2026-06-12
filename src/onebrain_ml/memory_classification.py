from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL_VERSION = "onebrain-memory-type-naive-bayes-v1"
RUNTIME_MODEL_PATH_ENV = "ONEBRAIN_MEMORY_CLASSIFIER_MODEL_PATH"

MEMORY_TYPES = (
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
)

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "com",
    "de",
    "do",
    "e",
    "for",
    "in",
    "is",
    "of",
    "or",
    "para",
    "the",
    "to",
    "um",
    "uma",
    "we",
    "with",
}


@dataclass(frozen=True)
class MemoryClassificationInput:
    relative_path: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)
    extension: str = ""
    title: str | None = None
    content: str = ""


@dataclass(frozen=True)
class MemoryClassificationResult:
    memory_type: str
    confidence: float
    method: str
    model_version: str = MODEL_VERSION
    reasons: list[str] = field(default_factory=list)
    runner_up: str | None = None
    runner_up_confidence: float | None = None

    def as_metadata(self) -> dict[str, object]:
        output: dict[str, object] = {
            "memory_type": self.memory_type,
            "confidence": round(self.confidence, 4),
            "method": self.method,
            "model_version": self.model_version,
            "reasons": list(self.reasons),
        }
        if self.runner_up:
            output["runner_up"] = self.runner_up
            output["runner_up_confidence"] = (
                round(self.runner_up_confidence, 4)
                if self.runner_up_confidence is not None
                else None
            )
        return output


@dataclass(frozen=True)
class TrainingExample:
    memory_type: str
    text: str
    relative_path: str = ""
    extension: str = ""
    title: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


class NaiveBayesMemoryClassifier:
    def __init__(self, examples: list[TrainingExample], *, balanced_priors: bool = False) -> None:
        self._balanced_priors = balanced_priors
        self._class_counts: Counter[str] = Counter()
        self._token_counts: dict[str, Counter[str]] = {
            memory_type: Counter() for memory_type in MEMORY_TYPES
        }
        self._token_totals: Counter[str] = Counter()
        self._vocabulary: set[str] = set()

        for example in examples:
            if example.memory_type not in MEMORY_TYPES:
                continue
            features = _features(
                MemoryClassificationInput(
                    relative_path=example.relative_path,
                    metadata=example.metadata,
                    extension=example.extension,
                    title=example.title,
                    content=example.text,
                )
            )
            if not features:
                continue
            self._class_counts[example.memory_type] += 1
            feature_counts = Counter(features)
            self._token_counts[example.memory_type].update(feature_counts)
            self._token_totals[example.memory_type] += sum(feature_counts.values())
            self._vocabulary.update(feature_counts)

    @classmethod
    def from_artifact(cls, artifact: Mapping[str, Any]) -> NaiveBayesMemoryClassifier:
        if artifact.get("model_version") != MODEL_VERSION:
            raise ValueError(
                f"unsupported memory classifier model version: {artifact.get('model_version')}"
            )

        classifier = cls([])
        class_counts = artifact.get("class_counts") or {}
        token_counts = artifact.get("token_counts") or {}
        token_totals = artifact.get("token_totals") or {}
        vocabulary = artifact.get("vocabulary") or []

        classifier._class_counts = Counter(
            {
                memory_type: int(count)
                for memory_type, count in dict(class_counts).items()
                if memory_type in MEMORY_TYPES
            }
        )
        classifier._token_counts = {
            memory_type: Counter(
                {
                    str(feature): int(count)
                    for feature, count in dict(token_counts.get(memory_type, {})).items()
                }
            )
            for memory_type in MEMORY_TYPES
        }
        classifier._token_totals = Counter(
            {
                memory_type: int(count)
                for memory_type, count in dict(token_totals).items()
                if memory_type in MEMORY_TYPES
            }
        )
        classifier._vocabulary = {str(feature) for feature in vocabulary}
        classifier._balanced_priors = bool(artifact.get("balanced_priors", False))
        return classifier

    def to_artifact(self) -> dict[str, object]:
        return {
            "model_version": MODEL_VERSION,
            "balanced_priors": self._balanced_priors,
            "memory_types": list(MEMORY_TYPES),
            "class_counts": dict(self._class_counts),
            "token_counts": {
                memory_type: dict(self._token_counts[memory_type]) for memory_type in MEMORY_TYPES
            },
            "token_totals": dict(self._token_totals),
            "vocabulary": sorted(self._vocabulary),
        }

    def classify(self, item: MemoryClassificationInput) -> MemoryClassificationResult:
        features = _features(item)
        if not features:
            return MemoryClassificationResult(
                memory_type="note",
                confidence=0.0,
                method="ml",
                reasons=["empty_feature_set"],
            )

        feature_counts = Counter(features)
        scores = {
            memory_type: self._score(memory_type, feature_counts) for memory_type in MEMORY_TYPES
        }
        probabilities = _softmax(scores)
        ranked = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        winner, confidence = ranked[0]
        runner_up, runner_up_confidence = ranked[1]
        return MemoryClassificationResult(
            memory_type=winner,
            confidence=confidence,
            method="ml",
            reasons=self._reasons(winner, runner_up, feature_counts),
            runner_up=runner_up,
            runner_up_confidence=runner_up_confidence,
        )

    def _score(self, memory_type: str, feature_counts: Counter[str]) -> float:
        total_examples = sum(self._class_counts.values())
        if self._balanced_priors:
            prior = 1 / len(MEMORY_TYPES)
        else:
            prior = (self._class_counts[memory_type] + 1) / (total_examples + len(MEMORY_TYPES))
        score = math.log(prior)
        vocabulary_size = max(len(self._vocabulary), 1)
        denominator = self._token_totals[memory_type] + vocabulary_size
        tokens = self._token_counts[memory_type]
        for feature, count in feature_counts.items():
            likelihood = (tokens[feature] + 1) / denominator
            score += min(count, 3) * math.log(likelihood)
        return score

    def _reasons(
        self,
        winner: str,
        runner_up: str,
        feature_counts: Counter[str],
    ) -> list[str]:
        evidence: list[tuple[float, str]] = []
        vocabulary_size = max(len(self._vocabulary), 1)
        winner_total = self._token_totals[winner] + vocabulary_size
        runner_up_total = self._token_totals[runner_up] + vocabulary_size
        for feature, count in feature_counts.items():
            winner_likelihood = (self._token_counts[winner][feature] + 1) / winner_total
            runner_up_likelihood = (self._token_counts[runner_up][feature] + 1) / runner_up_total
            weight = min(count, 3) * math.log(winner_likelihood / runner_up_likelihood)
            if weight > 0:
                evidence.append((weight, feature))
        return [_humanize_feature(feature) for _, feature in sorted(evidence, reverse=True)[:5]]


def classify_memory_type(item: MemoryClassificationInput) -> MemoryClassificationResult:
    return _runtime_classifier().classify(item)


def default_training_examples() -> list[TrainingExample]:
    return list(_seed_examples())


def load_memory_classifier(path: str | Path) -> NaiveBayesMemoryClassifier:
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    return NaiveBayesMemoryClassifier.from_artifact(artifact)


def save_memory_classifier(classifier: NaiveBayesMemoryClassifier, path: str | Path) -> None:
    model_path = Path(path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        json.dumps(classifier.to_artifact(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def clear_runtime_classifier_cache() -> None:
    _runtime_classifier_for_file.cache_clear()
    _seed_classifier.cache_clear()


def _runtime_classifier() -> NaiveBayesMemoryClassifier:
    if model_path := os.getenv(RUNTIME_MODEL_PATH_ENV):
        path = Path(model_path)
        if path.exists():
            return _runtime_classifier_for_file(str(path), path.stat().st_mtime_ns)
    return _seed_classifier()


@lru_cache(maxsize=4)
def _runtime_classifier_for_file(path: str, mtime_ns: int) -> NaiveBayesMemoryClassifier:
    return load_memory_classifier(path)


@lru_cache(maxsize=1)
def _seed_classifier() -> NaiveBayesMemoryClassifier:
    return NaiveBayesMemoryClassifier(_seed_examples())


def _features(item: MemoryClassificationInput) -> list[str]:
    features: list[str] = []
    extension = item.extension.lower().lstrip(".")
    if extension:
        features.append(f"ext:{extension}")

    path_tokens = _tokens(item.relative_path.replace("\\", " ").replace("/", " "))
    features.extend(f"path:{token}" for token in path_tokens)
    features.extend(path_tokens)

    metadata = {str(key).lower(): str(value) for key, value in item.metadata.items()}
    for key, value in sorted(metadata.items()):
        if value:
            features.append(f"meta:{key}:{_normalize(value)}")
            features.extend(f"meta:{key}:{token}" for token in _tokens(value))
            features.extend(_tokens(value))

    title_tokens = _tokens(item.title or "")
    features.extend(f"title:{token}" for token in title_tokens)
    features.extend(title_tokens)

    content_tokens = _tokens(item.content)
    features.extend(content_tokens)
    features.extend(_bigrams(content_tokens[:240]))
    return features


def _tokens(value: str) -> list[str]:
    normalized = _normalize(value)
    return [token for token in TOKEN_PATTERN.findall(normalized) if token not in STOPWORDS]


def _bigrams(tokens: list[str]) -> list[str]:
    return [f"bigram:{left}_{right}" for left, right in zip(tokens, tokens[1:], strict=False)]


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9_.:-]+", " ", without_accents)


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    max_score = max(scores.values())
    exponents = {label: math.exp(score - max_score) for label, score in scores.items()}
    total = sum(exponents.values())
    return {label: value / total for label, value in exponents.items()}


def _humanize_feature(feature: str) -> str:
    if feature.startswith("bigram:"):
        return feature.removeprefix("bigram:").replace("_", " ")
    if feature.startswith("path:"):
        return f"path contains {feature.removeprefix('path:')}"
    if feature.startswith("title:"):
        return f"title contains {feature.removeprefix('title:')}"
    if feature.startswith("ext:"):
        return f"extension {feature.removeprefix('ext:')}"
    if feature.startswith("meta:"):
        return feature.replace(":", " ")
    return f"text contains {feature}"


def _seed_examples() -> list[TrainingExample]:
    return [
        TrainingExample(
            "rule",
            (
                "Must always validate API keys before accepting requests. "
                "Never store secrets as memories."
            ),
            title="Runtime rule",
        ),
        TrainingExample(
            "rule",
            "Regra: deve usar HTTPS em producao e nao deve expor Postgres publicamente.",
        ),
        TrainingExample(
            "rule",
            "Feedback says Wait For Response should be used when request metadata is needed.",
            metadata={"type": "feedback"},
        ),
        TrainingExample(
            "preference",
            "User prefers concise Portuguese answers with practical engineering detail.",
            title="User preference",
        ),
        TrainingExample(
            "preference",
            "Prefer Python for experimentation and keep UI copy in English.",
        ),
        TrainingExample(
            "workflow",
            (
                "Checklist: run tests, inspect logs, deploy, verify health checks, "
                "then notify stakeholders."
            ),
            relative_path="playbooks/release-checklist.md",
        ),
        TrainingExample(
            "workflow",
            (
                "Fluxo de trabalho: primeiro analisar, depois implementar, "
                "testar e abrir pull request."
            ),
        ),
        TrainingExample(
            "skill",
            (
                "Use this skill when reviewing pull requests. "
                "Instructions: inspect risks and missing tests."
            ),
            relative_path="skills/pr-reviewer/SKILL.md",
            extension=".md",
        ),
        TrainingExample(
            "skill",
            "Capabilities: code review, test strategy. Tools: search, shell, git.",
            metadata={"type": "skill"},
        ),
        TrainingExample(
            "decision",
            (
                "ADR: Accepted. We decided to use PostgreSQL as canonical storage. "
                "Consequences include migrations."
            ),
            title="Architecture decision",
        ),
        TrainingExample(
            "decision",
            "Decisao: manter Python em vez de migrar para .NET neste momento.",
        ),
        TrainingExample(
            "pitfall",
            (
                "Pitfall: avoid using Wait For Request because it returns only the URL "
                "and misses headers."
            ),
            title="Known pitfall",
        ),
        TrainingExample(
            "pitfall",
            "Known risk: avoid changing vector size without recreating the collection.",
            relative_path="risks/vector-size.md",
            title="Vector size pitfall",
        ),
        TrainingExample(
            "pitfall",
            "Gotcha: this failure mode causes broken imports and should be avoided.",
            relative_path="pitfalls/import-failure.md",
        ),
        TrainingExample(
            "pitfall",
            "Armadilha: nao assumir que a colecao Qdrant aceita outro tamanho de vetor.",
        ),
        TrainingExample(
            "context",
            (
                "Project overview, repository layout, architecture background, "
                "bounded context, and current state."
            ),
            relative_path="project_overview.md",
        ),
        TrainingExample(
            "context",
            "Contexto do projeto: servico de memoria com Postgres, Qdrant, API, Web e MCP.",
        ),
        TrainingExample(
            "runbook",
            (
                "Runbook: when alerts fire, check service health, inspect logs, "
                "restart worker, and rollback if needed."
            ),
            relative_path="runbooks/incident-response.md",
        ),
        TrainingExample(
            "runbook",
            "Troubleshooting procedure for production incident and recovery steps.",
        ),
        TrainingExample(
            "fact",
            (
                "Configuration field ONEBRAIN_VECTOR_SIZE defaults to 384 "
                "and controls embedding dimensions."
            ),
            extension=".env",
        ),
        TrainingExample(
            "fact",
            "The API endpoint /api/v1/search accepts a query, limit, and filters object.",
        ),
        TrainingExample(
            "fact",
            "class MemoryCreate defines memory_type, title, content, scope, tags, and source.",
            extension=".py",
        ),
        TrainingExample(
            "note",
            "Meeting note: discussed next ideas, open questions, and possible follow-up items.",
        ),
        TrainingExample(
            "note",
            "Nota livre com observacoes soltas, ideias e lembretes que ainda nao viraram regra.",
        ),
    ]
