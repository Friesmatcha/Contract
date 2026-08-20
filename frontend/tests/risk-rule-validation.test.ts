import { expect, test } from 'vitest'

import type { RiskRuleCondition, RiskRuleInput } from '@/api/types'
import {
  normalizeRiskRule,
  validateRiskRuleCondition,
  validateRiskRules,
} from '@/features/risk-rules/validation'

function rule(overrides: Partial<RiskRuleInput> = {}): RiskRuleInput {
  return {
    rule_key: 'payment_terms_missing',
    risk_type: 'payment_terms',
    engine: 'deterministic',
    condition: { operator: 'field_missing', field: 'payment_terms' },
    severity: 'medium',
    suggestion: '请复核付款条件。',
    enabled: true,
    ...overrides,
  }
}

test('accepts nested whitelisted conditions', () => {
  expect(
    validateRiskRules([
      rule({
        condition: {
          operator: 'all',
          conditions: [
            { operator: 'keyword', field: 'contract_text', value: '无限责任' },
            {
              operator: 'not',
              condition: { operator: 'field_exists', field: 'performance_period' },
            },
          ],
        },
      }),
    ]),
  ).toBeNull()
})

test('rejects unknown and operator-incompatible fields', () => {
  const unknown = {
    operator: 'field_missing',
    field: 'organization_id',
  } as unknown as RiskRuleCondition
  const wrongKeywordField = {
    operator: 'keyword',
    field: 'payment_terms',
    value: '付款',
  } as unknown as RiskRuleCondition

  expect(validateRiskRuleCondition(unknown, 'deterministic')).toBe('请选择受支持的结构化字段。')
  expect(validateRiskRuleCondition(wrongKeywordField, 'deterministic')).toBe(
    '关键词条件需要选择合同全文并填写关键词。',
  )
})

test('rejects invalid thresholds and nested semantic conditions', () => {
  expect(
    validateRiskRuleCondition(
      {
        operator: 'amount_threshold',
        field: 'contract_amount',
        comparison: 'gte',
        value: 'NaN',
      },
      'deterministic',
    ),
  ).toContain('十进制')
  expect(
    validateRiskRuleCondition(
      {
        operator: 'date_threshold',
        field: 'signing_date',
        comparison: 'lt',
        value: '2026-02-30',
      },
      'deterministic',
    ),
  ).toContain('有效日期')
  expect(
    validateRiskRuleCondition(
      {
        operator: 'not',
        condition: { operator: 'semantic' },
      },
      'deterministic',
    ),
  ).toBe('确定性引擎不能使用语义条件。')
})

test('enforces rule count and unique rule keys', () => {
  expect(validateRiskRules([])).toBe('规则版本必须包含 1 到 200 条规则。')
  expect(validateRiskRules([rule(), rule()])).toBe('第 2 条规则：规则键与前面的规则重复。')
  expect(
    validateRiskRules(
      Array.from({ length: 201 }, (_, index) => rule({ rule_key: `rule_${index}` })),
    ),
  ).toBe('规则版本必须包含 1 到 200 条规则。')
})

test('normalizes decimal payloads after whitespace-tolerant validation', () => {
  const normalized = normalizeRiskRule(
    rule({
      rule_key: ' payment_limit ',
      condition: {
        operator: 'amount_threshold',
        field: 'contract_amount',
        comparison: 'gte',
        value: ' 100.00 ',
      },
    }),
  )

  expect(normalized.rule_key).toBe('payment_limit')
  expect(normalized.condition).toMatchObject({ value: '100.00' })
  expect(validateRiskRules([normalized])).toBeNull()
})
