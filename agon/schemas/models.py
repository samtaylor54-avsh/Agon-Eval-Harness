"""Core data schemas for the Agon Eval Harness.

These models are normative. They adapt PRD §23 to the Inspect-AI build, applying the
corrections recorded in the build plan / ADR-0001:

- The canonical test-case input is the nested ``input:`` block (``user_message`` /
  ``documents``), matching the PRD §27 example — NOT the flat ``user_input`` of §23.1.
- ``ScoringSpec`` gains an ``advisory`` flag (referenced by the composite rule, §25.13)
  and enforces ``pass_threshold == 1.0`` for safety scorers (§25.12).
- We do NOT reimplement the SQLite result payloads of §23.4; Inspect's ``EvalLog`` is the
  results store. Only harness-owned outputs (regression, review, recommendation) live here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

SAFETY_SCORER_TYPE = "safety"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADVERSARIAL = "adversarial"


class Recommendation(StrEnum):
    PASS = "PASS"
    INVESTIGATE = "INVESTIGATE"
    FAIL = "FAIL"


# --------------------------------------------------------------------------- #
# Test-case input schema
# --------------------------------------------------------------------------- #
class ScoringSpec(BaseModel):
    """One scorer applied to a test case, with weight + pass threshold."""

    model_config = ConfigDict(extra="forbid")

    type: str  # must match a registered Scorer key, e.g. "exact_match"
    weight: float = Field(1.0, ge=0.0)  # relative weight in the composite
    pass_threshold: float = Field(0.5, ge=0.0, le=1.0)
    # An advisory scorer is reported but does NOT gate the case's pass/fail (§25.13).
    advisory: bool = False
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _enforce_safety_threshold(self) -> ScoringSpec:
        # Safety scorers are binary-critical: they cannot pass below a perfect score.
        if self.type == SAFETY_SCORER_TYPE and self.pass_threshold != 1.0:
            raise ValueError(
                "safety scorers must have pass_threshold == 1.0 (binary-critical, §25.12)"
            )
        return self


class ExpectedBehavior(BaseModel):
    """Reference / expectations a scorer checks the SUT response against."""

    model_config = ConfigDict(extra="forbid")

    expected_answer: str | None = None
    answer_contains: list[str] = Field(default_factory=list)
    answer_not_contains: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    citation_required: bool = False
    allowed_sources: list[str] = Field(default_factory=list)
    expected_tool_calls: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    # JSON Schema for structured-output validation (json_schema scorer).
    json_schema: dict[str, Any] | None = None


class CaseInput(BaseModel):
    """The challenge presented to the system under test (canonical ``input:`` block)."""

    model_config = ConfigDict(extra="forbid")

    user_message: str
    documents: list[str] = Field(default_factory=list)
    session_id: str | None = None
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class AgonCase(BaseModel):
    """A single evaluation test case (PRD §8.1 / §23.1, reconciled)."""

    model_config = ConfigDict(extra="forbid")

    test_id: str = Field(pattern=r"^[a-z0-9_\-]+$")
    name: str
    category: str
    input: CaseInput
    risk_level: RiskLevel = RiskLevel.MEDIUM
    difficulty_level: Difficulty = Difficulty.MEDIUM
    expected: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    scoring: list[ScoringSpec] = Field(min_length=1)
    failure_labels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    repetitions: int | None = Field(default=None, ge=1)  # overrides RunConfig.epochs
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgonDataset(BaseModel):
    """A validated, content-addressed collection of test cases."""

    model_config = ConfigDict(extra="forbid")

    name: str
    dataset_version: str  # sha256 of canonicalized cases, computed by the loader
    test_cases: list[AgonCase] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Run configuration
# --------------------------------------------------------------------------- #
class SUTConfig(BaseModel):
    """How to reach the System Under Test. Defaults to the offline mock provider."""

    model_config = ConfigDict(extra="forbid")

    adapter: str = "mockllm"  # "mockllm" | "litellm" | "http" | "callable"
    model: str | None = None  # e.g. "openai/gpt-4o"; ignored for http/callable
    temperature: float = 0.0
    seed: int | None = 42
    system_prompt: str | None = None
    prompt_version: str = "unversioned"
    endpoint_url: str | None = None  # http adapter
    headers: dict[str, str] = Field(default_factory=dict)
    field_map: dict[str, str] = Field(default_factory=dict)  # http response -> SUTResponse
    extra: dict[str, Any] = Field(default_factory=dict)


class JudgeConfig(BaseModel):
    """LLM-as-judge configuration. Offline default uses the mock provider."""

    model_config = ConfigDict(extra="forbid")

    model: str = "mockllm/model"
    temperature: float = 0.0
    seed: int | None = 42
    max_tokens: int = 1024


class RunConfig(BaseModel):
    """Top-level run configuration (harness-owned; execution is delegated to Inspect)."""

    model_config = ConfigDict(extra="forbid")

    system_version: str = "unversioned"
    sut: SUTConfig = Field(default_factory=SUTConfig)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    epochs: int = Field(default=1, ge=1)  # repetitions per case
    flake_rule: str = "all"  # "all" | "any" | "majority"
    max_connections: int = Field(default=8, ge=1)
    fail_fast: bool = False
    baseline_run: str | None = None
    log_dir: str = "logs"
    report_dir: str = "reports"
    # Recommendation thresholds (§ report logic).
    pass_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    investigate_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_flake_rule(self) -> RunConfig:
        allowed = {"all", "any", "majority"}
        if self.flake_rule not in allowed:
            raise ValueError(f"flake_rule must be one of {sorted(allowed)}")
        if self.investigate_threshold > self.pass_threshold:
            raise ValueError("investigate_threshold must be <= pass_threshold")
        return self


# --------------------------------------------------------------------------- #
# Harness-owned outputs (Inspect's EvalLog owns per-sample results)
# --------------------------------------------------------------------------- #
class ReviewRecord(BaseModel):
    """A human review/override, appended alongside the immutable eval log (§8.7)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    test_id: str
    epoch: int = 1
    reviewer: str
    override_passed: bool | None = None
    override_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confirmed_failure_labels: list[str] = Field(default_factory=list)
    ambiguous: bool = False
    notes: str = ""
    timestamp: str  # ISO 8601 UTC


class RegressionReport(BaseModel):
    """Result of comparing a current run against a baseline run (§25.15)."""

    model_config = ConfigDict(extra="forbid")

    current_run_id: str
    baseline_run_id: str
    new_failures: list[str] = Field(default_factory=list)
    fixed_failures: list[str] = Field(default_factory=list)
    unchanged_failures: list[str] = Field(default_factory=list)
    score_drops: list[tuple[str, float, float]] = Field(default_factory=list)  # (id, old, new)
    score_improvements: list[tuple[str, float, float]] = Field(default_factory=list)
    category_regressions: dict[str, tuple[float, float]] = Field(default_factory=dict)
    regression_detected: bool = False
