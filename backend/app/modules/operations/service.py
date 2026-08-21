from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from backend.app.modules.contracts.models import Contract
from backend.app.modules.identity.models import PlatformModelConfiguration
from backend.app.modules.reviews.models import ModelCall, ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import RiskFinding
from backend.app.modules.reviews.revisions.models import ResultRevision
from backend.app.modules.warnings.models import Warning, WarningEvent
from backend.app.shared.errors import ApplicationError


def _metrics_not_enabled() -> ApplicationError:
    return ApplicationError(
        status_code=501,
        code="METRICS_NOT_ENABLED",
        message="运营指标尚未启用。",
    )


def ensure_metrics_enabled(session: Session) -> None:
    configuration = session.scalar(
        select(PlatformModelConfiguration).where(PlatformModelConfiguration.singleton_key == 1)
    )
    if configuration is None or not configuration.usage_tracking_enabled:
        raise _metrics_not_enabled()


def review_metrics(
    session: Session,
    *,
    organization_id: UUID,
    from_: datetime,
    to: datetime,
    contract_type: str | None,
) -> dict[str, object]:
    task_statement = select(ReviewTask).where(
        ReviewTask.organization_id == organization_id,
        ReviewTask.created_at >= from_,
        ReviewTask.created_at < to,
    )
    if contract_type is not None:
        task_statement = task_statement.join(
            Contract,
            (Contract.organization_id == ReviewTask.organization_id)
            & (Contract.id == ReviewTask.contract_id),
        ).where(Contract.declared_type == contract_type)
    tasks = list(session.scalars(task_statement))
    task_ids = [task.id for task in tasks]
    task_count = len(tasks)
    terminal_durations = [
        int((task.finished_at - task.started_at).total_seconds() * 1000)
        for task in tasks
        if task.status in {"completed", "failed"}
        and task.started_at is not None
        and task.finished_at is not None
    ]

    parse_runs: list[ReviewStageRun] = []
    model_calls: list[ModelCall] = []
    if task_ids:
        parse_runs = list(
            session.scalars(
                select(ReviewStageRun).where(
                    ReviewStageRun.organization_id == organization_id,
                    ReviewStageRun.review_task_id.in_(task_ids),
                    ReviewStageRun.stage == "parsing",
                )
            )
        )
        model_calls = list(
            session.scalars(
                select(ModelCall).where(
                    ModelCall.organization_id == organization_id,
                    ModelCall.review_task_id.in_(task_ids),
                )
            )
        )
        edited_task_ids = set(
            session.scalars(
                select(ResultRevision.review_task_id)
                .where(
                    ResultRevision.organization_id == organization_id,
                    ResultRevision.review_task_id.in_(task_ids),
                )
                .distinct()
            )
        )
    else:
        edited_task_ids = set()

    return {
        "from": from_,
        "to": to,
        "review_count": task_count,
        "completed_count": sum(task.status == "completed" for task in tasks),
        "failed_count": sum(task.status == "failed" for task in tasks),
        "average_duration_ms": round(sum(terminal_durations) / len(terminal_durations))
        if terminal_durations
        else 0,
        "parse_failure_rate": sum(run.status == "failed" for run in parse_runs) / len(parse_runs)
        if parse_runs
        else 0.0,
        "model_failure_rate": (
            sum(call.status == "failed" for call in model_calls) / len(model_calls)
            if model_calls
            else 0.0
        ),
        "manual_edit_rate": len(edited_task_ids) / task_count if task_count else 0.0,
    }


def warning_metrics(
    session: Session,
    *,
    organization_id: UUID,
    from_: datetime,
    to: datetime,
    risk_type: str | None,
    severity: str | None,
) -> dict[str, object]:
    statement = select(Warning).where(
        Warning.organization_id == organization_id,
        Warning.triggered_at >= from_,
        Warning.triggered_at < to,
    )
    if severity is not None:
        statement = statement.where(Warning.severity == severity)
    if risk_type is not None:
        statement = statement.where(
            exists(
                select(RiskFinding.id).where(
                    RiskFinding.organization_id == organization_id,
                    RiskFinding.id == Warning.risk_finding_id,
                    RiskFinding.risk_type == risk_type,
                )
            )
            | (Warning.risk_finding_id.is_(None) & (Warning.trigger_type == risk_type))
        )
    warnings = list(session.scalars(statement))
    warning_ids = [warning.id for warning in warnings]
    false_positive_ids = set()
    if warning_ids:
        false_positive_ids = set(
            session.scalars(
                select(WarningEvent.warning_id).where(
                    WarningEvent.organization_id == organization_id,
                    WarningEvent.warning_id.in_(warning_ids),
                    WarningEvent.event_type == "false_positive",
                )
            )
        )
    risk_ids = [warning.risk_finding_id for warning in warnings if warning.risk_finding_id]
    risk_types: dict[UUID, str] = (
        {
            row[0]: row[1]
            for row in session.execute(
                select(RiskFinding.id, RiskFinding.risk_type).where(
                    RiskFinding.organization_id == organization_id,
                    RiskFinding.id.in_(risk_ids),
                )
            ).all()
        }
        if risk_ids
        else {}
    )
    breakdown: Counter[str] = Counter()
    for warning in warnings:
        risk_type = (
            risk_types.get(warning.risk_finding_id, warning.trigger_type)
            if warning.risk_finding_id is not None
            else warning.trigger_type
        )
        breakdown[risk_type] += 1
    unprocessed = [
        warning
        for warning in warnings
        if warning.status in {"pending_confirmation", "in_progress"}
    ]
    now = datetime.now(UTC)
    durations = [
        max(0, int((now - warning.triggered_at).total_seconds() * 1000))
        for warning in unprocessed
    ]
    count = len(warnings)
    closed = sum(warning.status == "closed" for warning in warnings)
    return {
        "from": from_,
        "to": to,
        "created_count": count,
        "unprocessed_count": len(unprocessed),
        "closed_count": closed,
        "closure_rate": closed / count if count else 0.0,
        "false_positive_rate": len(false_positive_ids) / count if count else 0.0,
        "average_unprocessed_duration_ms": (
            round(sum(durations) / len(durations)) if durations else 0
        ),
        "by_risk_type": [
            {"risk_type": key, "count": value} for key, value in sorted(breakdown.items())
        ],
    }
