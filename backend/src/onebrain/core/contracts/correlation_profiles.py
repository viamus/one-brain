from __future__ import annotations

from dataclasses import asdict, dataclass

DEFAULT_CORRELATION_SCORING_PROFILE = "deterministic-v1"
EXECUTABLE_CORRELATION_PROFILE_STATUSES = {"available", "experimental"}


@dataclass(frozen=True)
class CorrelationScoringProfile:
    key: str
    label: str
    summary: str
    score_version: str
    model_family: str
    status: str
    online_safe: bool
    requires_training: bool

    @property
    def executable(self) -> bool:
        return self.status in EXECUTABLE_CORRELATION_PROFILE_STATUSES

    def to_public_dict(self) -> dict[str, str | bool]:
        payload = asdict(self)
        payload["executable"] = self.executable
        return payload


CORRELATION_SCORING_PROFILES = (
    CorrelationScoringProfile(
        key="deterministic-v1",
        label="Deterministic v1",
        summary=(
            "Current production-safe shared entity, semantic facet, "
            "and vector-neighbor scorer."
        ),
        score_version="deterministic-v1",
        model_family="deterministic",
        status="available",
        online_safe=True,
        requires_training=False,
    ),
    CorrelationScoringProfile(
        key="deterministic-v2",
        label="Deterministic v2",
        summary="Experimental deterministic tuning with richer facet tail weighting for A/B runs.",
        score_version="deterministic-v2",
        model_family="deterministic",
        status="experimental",
        online_safe=True,
        requires_training=False,
    ),
    CorrelationScoringProfile(
        key="logistic-regression-v1",
        label="Logistic regression",
        summary="Planned supervised edge scorer for calibrated probability from graph features.",
        score_version="logistic-regression-v1",
        model_family="linear",
        status="planned",
        online_safe=False,
        requires_training=True,
    ),
    CorrelationScoringProfile(
        key="decision-tree-v1",
        label="Decision tree",
        summary="Planned explainable classifier for rules discovered from accepted/rejected links.",
        score_version="decision-tree-v1",
        model_family="tree",
        status="planned",
        online_safe=False,
        requires_training=True,
    ),
    CorrelationScoringProfile(
        key="domain-centroid-v1",
        label="Domain centroid",
        summary="Planned centroid scorer for domain and scope-aware cluster assignment.",
        score_version="domain-centroid-v1",
        model_family="centroid",
        status="planned",
        online_safe=False,
        requires_training=True,
    ),
    CorrelationScoringProfile(
        key="link-classifier-v1",
        label="Link classifier",
        summary="Planned relation classifier for explicit link-type prediction and confidence.",
        score_version="link-classifier-v1",
        model_family="classifier",
        status="planned",
        online_safe=False,
        requires_training=True,
    ),
)

CORRELATION_SCORING_PROFILE_BY_KEY = {
    profile.key: profile for profile in CORRELATION_SCORING_PROFILES
}


def correlation_scoring_profile(key: str | None) -> CorrelationScoringProfile:
    normalized = normalize_correlation_scoring_profile(key)
    return CORRELATION_SCORING_PROFILE_BY_KEY[normalized]


def correlation_scoring_profiles_payload() -> list[dict[str, str | bool]]:
    return [profile.to_public_dict() for profile in CORRELATION_SCORING_PROFILES]


def executable_correlation_scoring_profile_keys() -> list[str]:
    return [profile.key for profile in CORRELATION_SCORING_PROFILES if profile.executable]


def normalize_correlation_scoring_profile(
    value: str | None,
    *,
    require_executable: bool = False,
) -> str:
    candidate = (value or DEFAULT_CORRELATION_SCORING_PROFILE).strip().lower()
    if candidate not in CORRELATION_SCORING_PROFILE_BY_KEY:
        raise ValueError(f"unknown correlation scoring profile: {candidate}")
    profile = CORRELATION_SCORING_PROFILE_BY_KEY[candidate]
    if require_executable and not profile.executable:
        raise ValueError(
            f"correlation scoring profile {candidate} is registered but not executable"
        )
    return candidate
