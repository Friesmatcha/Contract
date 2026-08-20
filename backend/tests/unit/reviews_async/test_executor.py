import pytest

from backend.app.modules.reviews.service import FakeStageExecutor, StageExecutionError


def test_fake_stage_executor_only_runs_orchestration_callbacks() -> None:
    heartbeat_calls: list[str] = []
    executor = FakeStageExecutor()

    executor.execute("parsing", lambda: heartbeat_calls.append("heartbeat"))

    assert heartbeat_calls == ["heartbeat"]
    assert executor.executed_stages == ["parsing"]
    assert executor.compensated_stages == []


def test_fake_stage_executor_has_deterministic_failure_and_compensation() -> None:
    executor = FakeStageExecutor(failing_stages=["risk_analysis"])

    with pytest.raises(StageExecutionError, match="阶段执行失败"):
        executor.execute("risk_analysis", lambda: None)
    executor.compensate("risk_analysis")

    assert executor.executed_stages == ["risk_analysis"]
    assert executor.compensated_stages == ["risk_analysis"]
