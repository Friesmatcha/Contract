import pytest
from pydantic import ValidationError

from backend.app.modules.risks.rules.schemas import RiskRuleInput
from backend.app.modules.risks.rules.service import validate_rules
from backend.app.shared.errors import ApplicationError


def _rule(*, condition: dict[str, object], engine: str = "deterministic") -> RiskRuleInput:
    return RiskRuleInput(
        rule_key="rule",
        risk_type="contract_risk",
        engine=engine,
        condition=condition,
        severity="medium",
        suggestion="请复核相关条款。",
    )


@pytest.mark.parametrize(
    "condition",
    [
        {"operator": "keyword", "field": "contract_text", "value": "付款"},
        {"operator": "regex", "field": "contract_text", "pattern": r"付款\\s*期限"},
        {
            "operator": "amount_threshold",
            "field": "contract_amount",
            "comparison": "gte",
            "value": "100",
        },
        {
            "operator": "date_threshold",
            "field": "signing_date",
            "comparison": "lt",
            "value": "2026-01-01",
        },
        {"operator": "field_exists", "field": "payment_terms"},
        {"operator": "field_missing", "field": "payment_terms"},
        {
            "operator": "all",
            "conditions": [
                {"operator": "keyword", "field": "contract_text", "value": "付款"},
                {"operator": "field_exists", "field": "payment_terms"},
            ],
        },
        {
            "operator": "any",
            "conditions": [{"operator": "field_missing", "field": "payment_terms"}],
        },
        {
            "operator": "not",
            "condition": {
                "operator": "keyword",
                "field": "contract_text",
                "value": "无条件",
            },
        },
        {"operator": "semantic"},
    ],
)
def test_whitelisted_conditions_are_accepted(condition: dict[str, object]) -> None:
    rule = _rule(
        condition=condition,
        engine="model" if condition["operator"] == "semantic" else "deterministic",
    )
    validate_rules([rule])


@pytest.mark.parametrize(
    "condition",
    [
        {"operator": "python", "source": "__import__('os').system('id')"},
        {"operator": "sql", "query": "SELECT 1"},
        {
            "operator": "keyword",
            "field": "contract_text",
            "value": "付款",
            "expression": "x",
        },
        {"operator": "regex", "field": "contract_text", "pattern": "("},
        {"operator": "keyword", "field": "unknown_field", "value": "付款"},
        {"operator": "keyword", "field": "payment_terms", "value": "付款"},
        {
            "operator": "amount_threshold",
            "field": "contract_text",
            "comparison": "gte",
            "value": "10",
        },
    ],
)
def test_arbitrary_code_and_invalid_schema_are_rejected(
    condition: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _rule(condition=condition)


@pytest.mark.parametrize(
    "condition",
    [
        {"operator": "amount_threshold", "field": "contract_amount", "value": "10"},
        {
            "operator": "amount_threshold",
            "field": "contract_amount",
            "comparison": "gte",
            "value": "not-a-number",
        },
        {
            "operator": "amount_threshold",
            "field": "contract_amount",
            "comparison": "gte",
            "value": 10,
        },
        {
            "operator": "date_threshold",
            "field": "signing_date",
            "comparison": "lt",
            "value": "2026-02-30",
        },
    ],
)
def test_threshold_conditions_reject_missing_or_invalid_values(
    condition: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _rule(condition=condition)


def test_deterministic_engine_cannot_use_semantic_condition() -> None:
    with pytest.raises(ApplicationError) as error:
        validate_rules([_rule(condition={"operator": "semantic"})])
    assert error.value.code == "RULE_SCHEMA_INVALID"


def test_deterministic_engine_cannot_hide_semantic_in_composite_condition() -> None:
    rule = _rule(
        condition={
            "operator": "all",
            "conditions": [
                {"operator": "field_exists", "field": "payment_terms"},
                {"operator": "not", "condition": {"operator": "semantic"}},
            ],
        }
    )
    with pytest.raises(ApplicationError) as error:
        validate_rules([rule])
    assert error.value.code == "RULE_SCHEMA_INVALID"


@pytest.mark.parametrize("count", [0, 201])
def test_rule_count_must_be_between_one_and_two_hundred(count: int) -> None:
    rules = [
        RiskRuleInput(
            rule_key=f"rule_{index}",
            risk_type="contract_risk",
            engine="deterministic",
            condition={"operator": "field_exists", "field": "payment_terms"},
            severity="medium",
            suggestion="请复核相关条款。",
        )
        for index in range(count)
    ]
    with pytest.raises(ApplicationError) as error:
        validate_rules(rules)
    assert error.value.code == "RULE_SCHEMA_INVALID"


def test_condition_depth_is_limited_to_five_levels() -> None:
    condition: dict[str, object] = {"operator": "semantic"}
    for _ in range(5):
        condition = {"operator": "not", "condition": condition}
    rule = _rule(condition=condition, engine="model")
    with pytest.raises(ApplicationError) as error:
        validate_rules([rule])
    assert error.value.code == "RULE_SCHEMA_INVALID"


def test_condition_depth_checks_later_branches_after_semantic_match() -> None:
    too_deep: dict[str, object] = {"operator": "field_exists", "field": "payment_terms"}
    for _ in range(5):
        too_deep = {"operator": "not", "condition": too_deep}
    rule = _rule(
        condition={
            "operator": "any",
            "conditions": [
                {"operator": "semantic"},
                too_deep,
            ],
        },
        engine="model",
    )

    with pytest.raises(ApplicationError) as error:
        validate_rules([rule])
    assert error.value.code == "RULE_SCHEMA_INVALID"
