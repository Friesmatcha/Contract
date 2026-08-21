from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewMetricsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: datetime = Field(alias="from")
    to: datetime
    review_count: int
    completed_count: int
    failed_count: int
    average_duration_ms: int
    parse_failure_rate: float
    model_failure_rate: float
    manual_edit_rate: float


class WarningRiskTypeMetric(BaseModel):
    risk_type: str
    count: int


class WarningMetricsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: datetime = Field(alias="from")
    to: datetime
    created_count: int
    unprocessed_count: int
    closed_count: int
    closure_rate: float
    false_positive_rate: float
    average_unprocessed_duration_ms: int
    by_risk_type: list[WarningRiskTypeMetric]


__all__ = ["ReviewMetricsResponse", "WarningMetricsResponse"]
