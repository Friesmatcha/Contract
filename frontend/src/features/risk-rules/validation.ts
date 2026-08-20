import type {
  RiskRuleInput,
  RiskRuleCondition,
  RiskRuleEngine,
  RiskRulePresenceField,
} from '@/api/types'

export const riskRulePresenceFields: Array<{
  label: string
  value: RiskRulePresenceField
}> = [
  { label: '合同主体', value: 'parties' },
  { label: '签署日期', value: 'signing_date' },
  { label: '合同金额', value: 'contract_amount' },
  { label: '履行期限', value: 'performance_period' },
  { label: '争议解决', value: 'dispute_resolution' },
  { label: '付款条件', value: 'payment_terms' },
  { label: '自动续期', value: 'auto_renewal' },
  { label: '验收标准', value: 'acceptance_standard' },
  { label: '知识产权', value: 'intellectual_property' },
  { label: '数据合规', value: 'data_compliance' },
  { label: '不可抗力', value: 'force_majeure' },
]

const presenceFields = new Set<string>(riskRulePresenceFields.map((option) => option.value))
const comparisons = new Set(['gt', 'gte', 'lt', 'lte', 'eq'])

function validDecimal(value: string): boolean {
  return value.length <= 128 && /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/.test(value.trim())
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) return false
  const parsed = new Date(Date.UTC(year, month - 1, day))
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  )
}

function normalizeCondition(condition: RiskRuleCondition): RiskRuleCondition {
  if (condition.operator === 'keyword') {
    return { ...condition, value: condition.value.trim() }
  }
  if (condition.operator === 'amount_threshold' || condition.operator === 'date_threshold') {
    return { ...condition, value: condition.value.trim() }
  }
  if (condition.operator === 'all' || condition.operator === 'any') {
    return { ...condition, conditions: condition.conditions.map(normalizeCondition) }
  }
  if (condition.operator === 'not') {
    return { ...condition, condition: normalizeCondition(condition.condition) }
  }
  return { ...condition }
}

export function normalizeRiskRule(rule: RiskRuleInput): RiskRuleInput {
  return {
    ...rule,
    rule_key: rule.rule_key.trim(),
    risk_type: rule.risk_type.trim(),
    condition: normalizeCondition(rule.condition),
    suggestion: rule.suggestion.trim(),
  }
}

export function validateRiskRuleCondition(
  condition: RiskRuleCondition,
  engine: RiskRuleEngine,
  depth = 1,
): string | null {
  if (depth > 5) return '条件嵌套不能超过 5 层。'
  if (condition.operator === 'keyword') {
    if (condition.field !== 'contract_text' || !condition.value.trim()) {
      return '关键词条件需要选择合同全文并填写关键词。'
    }
    if (condition.value.length > 2000) return '关键词不能超过 2000 个字符。'
    return null
  }
  if (condition.operator === 'regex') {
    if (condition.field !== 'contract_text' || !condition.pattern.trim()) {
      return '正则条件需要选择合同全文并填写模式。'
    }
    if (condition.pattern.length > 1000) return '正则模式不能超过 1000 个字符。'
    try {
      new RegExp(condition.pattern)
    } catch {
      return '正则模式无效，请检查语法。'
    }
    return null
  }
  if (condition.operator === 'field_exists' || condition.operator === 'field_missing') {
    return presenceFields.has(condition.field) ? null : '请选择受支持的结构化字段。'
  }
  if (condition.operator === 'amount_threshold') {
    if (
      condition.field !== 'contract_amount' ||
      !comparisons.has(condition.comparison) ||
      !validDecimal(condition.value)
    ) {
      return '金额阈值需要选择合同金额、比较方式和十进制数值。'
    }
    return null
  }
  if (condition.operator === 'date_threshold') {
    if (
      condition.field !== 'signing_date' ||
      !comparisons.has(condition.comparison) ||
      !validDate(condition.value)
    ) {
      return '日期阈值需要选择签署日期、比较方式和有效日期。'
    }
    return null
  }
  if (condition.operator === 'all' || condition.operator === 'any') {
    if (condition.conditions.length < 1 || condition.conditions.length > 20) {
      return '组合条件需要包含 1 到 20 个子条件。'
    }
    for (const child of condition.conditions) {
      const error = validateRiskRuleCondition(child, engine, depth + 1)
      if (error) return error
    }
    return null
  }
  if (condition.operator === 'not') {
    return validateRiskRuleCondition(condition.condition, engine, depth + 1)
  }
  if (condition.operator === 'semantic' && engine === 'deterministic') {
    return '确定性引擎不能使用语义条件。'
  }
  return null
}

export function validateRiskRule(rule: RiskRuleInput): string | null {
  const ruleKey = rule.rule_key.trim()
  const riskType = rule.risk_type.trim()
  const suggestion = rule.suggestion.trim()
  if (!ruleKey || !riskType || !suggestion) return '请填写规则键、风险类型和建议。'
  if (ruleKey.length > 128 || riskType.length > 128) return '规则键和风险类型不能超过 128 个字符。'
  if (suggestion.length > 2000) return '建议不能超过 2000 个字符。'
  return validateRiskRuleCondition(rule.condition, rule.engine)
}

export function validateRiskRules(rules: RiskRuleInput[]): string | null {
  if (rules.length < 1 || rules.length > 200) return '规则版本必须包含 1 到 200 条规则。'
  const keys = new Set<string>()
  for (const [index, rule] of rules.entries()) {
    const error = validateRiskRule(rule)
    if (error) return `第 ${index + 1} 条规则：${error}`
    const key = rule.rule_key.trim()
    if (keys.has(key)) return `第 ${index + 1} 条规则：规则键与前面的规则重复。`
    keys.add(key)
  }
  return null
}
