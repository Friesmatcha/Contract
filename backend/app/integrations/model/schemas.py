from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ModelCapability = Literal[
    "classification",
    "extraction",
    "risk_analysis",
    "clause_comparison",
]

DEFAULT_PROMPT_VERSION = "platform-baseline-v1"
DEFAULT_SCHEMA_VERSION = "model-schema-v1"
DEFAULT_SANITIZATION_POLICY_VERSION = "sanitization-v1"


class ModelSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelRequest(ModelSchema):
    input_text: str = Field(min_length=1, max_length=5_000_000)
    input_version: str = Field(default="input-v1", min_length=1, max_length=128)
    prompt_version: str = Field(
        default=DEFAULT_PROMPT_VERSION, min_length=1, max_length=128
    )
    schema_version: str = Field(
        default=DEFAULT_SCHEMA_VERSION, min_length=1, max_length=128
    )
    sanitization_policy_version: str = Field(
        default=DEFAULT_SANITIZATION_POLICY_VERSION, min_length=1, max_length=128
    )
    context: dict[str, str] = Field(default_factory=dict)


class ClassificationRequest(ModelRequest):
    pass


class ExtractionRequest(ModelRequest):
    pass


class RiskAnalysisRequest(ModelRequest):
    pass


class ClauseComparisonRequest(ModelRequest):
    pass


class Evidence(ModelSchema):
    source_span_id: str = Field(min_length=1, max_length=128)
    quote: str = Field(min_length=1, max_length=2_000)


class ModelResult(ModelSchema):
    evidence: list[Evidence] = Field(min_length=1, max_length=50)


class ClassificationResult(ModelResult):
    category: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)


class ExtractedField(ModelSchema):
    field_key: str = Field(min_length=1, max_length=128)
    value: Any | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(min_length=1, max_length=50)


class ExtractionResult(ModelResult):
    fields: list[ExtractedField] = Field(min_length=1, max_length=256)


class RiskFinding(ModelSchema):
    risk_type: str = Field(min_length=1, max_length=128)
    severity: Literal["high", "medium", "low"]
    title: str = Field(min_length=1, max_length=255)
    basis: str = Field(min_length=1, max_length=2_000)
    evidence: list[Evidence] = Field(min_length=1, max_length=50)


class RiskAnalysisResult(ModelResult):
    findings: list[RiskFinding] = Field(min_length=1, max_length=256)


class ClauseComparison(ModelSchema):
    clause_key: str = Field(min_length=1, max_length=128)
    result: Literal["match", "deviation", "missing", "not_applicable"]
    explanation: str = Field(min_length=1, max_length=2_000)
    evidence: list[Evidence] = Field(min_length=1, max_length=50)


class ClauseComparisonResult(ModelResult):
    comparisons: list[ClauseComparison] = Field(min_length=1, max_length=256)


__all__ = [
    "ClauseComparison",
    "ClauseComparisonRequest",
    "ClauseComparisonResult",
    "ClassificationRequest",
    "ClassificationResult",
    "DEFAULT_PROMPT_VERSION",
    "DEFAULT_SANITIZATION_POLICY_VERSION",
    "DEFAULT_SCHEMA_VERSION",
    "Evidence",
    "ExtractedField",
    "ExtractionRequest",
    "ExtractionResult",
    "ModelCapability",
    "ModelRequest",
    "ModelResult",
    "RiskAnalysisRequest",
    "RiskAnalysisResult",
    "RiskFinding",
]
