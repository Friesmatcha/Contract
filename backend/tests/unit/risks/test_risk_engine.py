from uuid import uuid4

import pytest

from backend.app.modules.reviews.results.service import _condition_value


@pytest.mark.parametrize(
    ("rule_key", "condition", "text", "values", "expected"),
    [
        (
            "unlimited_liability",
            {"operator": "keyword", "field": "contract_text", "value": "无限责任"},
            "乙方承担无限责任。",
            {},
            True,
        ),
        (
            "unlimited_liability_negative",
            {"operator": "keyword", "field": "contract_text", "value": "无限责任"},
            "乙方责任以合同金额为上限。",
            {},
            False,
        ),
        (
            "excessive_liquidated_damages",
            {"operator": "keyword", "field": "contract_text", "value": "违约金"},
            "违约金按日计算。",
            {},
            True,
        ),
        (
            "unilateral_termination",
            {"operator": "keyword", "field": "contract_text", "value": "单方解除"},
            "甲方可以单方解除合同。",
            {},
            True,
        ),
        (
            "broad_confidentiality_negative",
            {"operator": "keyword", "field": "contract_text", "value": "永久保密"},
            "保密义务在终止后两年届满。",
            {},
            False,
        ),
        (
            "auto_renewal",
            {"operator": "keyword", "field": "contract_text", "value": "自动续期"},
            "合同期满后自动续期。",
            {},
            True,
        ),
        (
            "unclear_payment",
            {"operator": "field_missing", "field": "payment_terms"},
            "双方约定交付方式。",
            {"payment_terms": None},
            True,
        ),
        (
            "unclear_payment_negative",
            {"operator": "field_missing", "field": "payment_terms"},
            "验收后30日内付款。",
            {"payment_terms": {"value": "验收后30日内付款"}},
            False,
        ),
        (
            "missing_acceptance_negative",
            {"operator": "field_missing", "field": "acceptance_standard"},
            "验收标准由双方另行确认。",
            {},
            False,
        ),
        (
            "unclear_ip",
            {"operator": "field_missing", "field": "intellectual_property"},
            "双方未约定交付物权利归属。",
            {},
            True,
        ),
        (
            "data_compliance_negative",
            {"operator": "field_missing", "field": "data_compliance"},
            "双方遵守数据合规和个人信息保护要求。",
            {},
            False,
        ),
        (
            "unfavorable_dispute",
            {"operator": "field_missing", "field": "dispute_resolution"},
            "本合同未约定争议解决方式。",
            {"dispute_resolution": None},
            True,
        ),
        (
            "force_majeure_negative",
            {"operator": "field_missing", "field": "force_majeure"},
            "不可抗力发生时双方互不承担违约责任。",
            {},
            False,
        ),
    ],
)
def test_baseline_risk_rules_have_positive_and_negative_examples(
    rule_key: str,
    condition: dict[str, object],
    text: str,
    values: dict[str, object],
    expected: bool,
) -> None:
    matched, _ = _condition_value(
        condition,
        text=text,
        values=values,
        evidence={},
        first_span=uuid4(),
    )

    assert matched is expected, rule_key


@pytest.mark.parametrize(
    ("condition", "values", "expected"),
    [
        (
            {
                "operator": "amount_threshold",
                "field": "contract_amount",
                "comparison": "gte",
                "value": "100000",
            },
            {"contract_amount": {"amount": "100000.00"}},
            True,
        ),
        (
            {
                "operator": "date_threshold",
                "field": "signing_date",
                "comparison": "lt",
                "value": "2026-01-01",
            },
            {"signing_date": "2025-12-31"},
            True,
        ),
        (
            {
                "operator": "all",
                "conditions": [
                    {"operator": "keyword", "field": "contract_text", "value": "甲方"},
                    {"operator": "keyword", "field": "contract_text", "value": "乙方"},
                ],
            },
            {},
            True,
        ),
        (
            {
                "operator": "not",
                "condition": {
                    "operator": "keyword",
                    "field": "contract_text",
                    "value": "无限责任",
                },
            },
            {},
            True,
        ),
    ],
)
def test_threshold_and_logical_rules_cover_positive_cases(
    condition: dict[str, object], values: dict[str, object], expected: bool
) -> None:
    matched, _ = _condition_value(
        condition,
        text="甲方与乙方签署合同。",
        values=values,
        evidence={},
        first_span=uuid4(),
    )

    assert matched is expected


def test_keyword_rule_handles_cross_sentence_text() -> None:
    matched, _ = _condition_value(
        {"operator": "regex", "field": "contract_text", "pattern": r"甲方.*乙方"},
        text="甲方承担通知义务。\n乙方承担付款义务。",
        values={},
        evidence={},
        first_span=uuid4(),
    )

    assert matched
