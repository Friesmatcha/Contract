<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type {
  RiskRuleComparison,
  RiskRuleCondition,
  RiskRuleEngine,
  RiskRuleField,
} from '@/api/types'
import { riskRulePresenceFields } from '@/features/risk-rules/validation'

type ConditionOperator = RiskRuleCondition['operator']

const props = withDefaults(
  defineProps<{
    modelValue: RiskRuleCondition
    engine: RiskRuleEngine
    depth?: number
  }>(),
  { depth: 1 },
)

const emit = defineEmits<{
  'update:modelValue': [value: RiskRuleCondition]
}>()

const baseOptions: Array<{ label: string; value: ConditionOperator }> = [
  { label: '关键词', value: 'keyword' },
  { label: '正则', value: 'regex' },
  { label: '金额阈值', value: 'amount_threshold' },
  { label: '日期阈值', value: 'date_threshold' },
  { label: '字段存在', value: 'field_exists' },
  { label: '字段缺失', value: 'field_missing' },
  { label: '语义判断', value: 'semantic' },
  { label: '全部满足', value: 'all' },
  { label: '任一满足', value: 'any' },
  { label: '不满足', value: 'not' },
]

const operatorOptions = computed(() =>
  baseOptions.filter((option) => {
    if (props.engine === 'deterministic' && option.value === 'semantic') return false
    if (props.depth >= 5 && ['all', 'any', 'not'].includes(option.value)) return false
    return true
  }),
)

const children = computed(() =>
  props.modelValue.operator === 'all' || props.modelValue.operator === 'any'
    ? props.modelValue.conditions
    : [],
)

const notChild = computed(() =>
  props.modelValue.operator === 'not' ? props.modelValue.condition : null,
)
const fieldOptions = computed<Array<{ label: string; value: RiskRuleField }>>(() => {
  if (props.modelValue.operator === 'keyword' || props.modelValue.operator === 'regex') {
    return [{ label: '合同全文', value: 'contract_text' }]
  }
  if (props.modelValue.operator === 'amount_threshold') {
    return [{ label: '合同金额', value: 'contract_amount' }]
  }
  if (props.modelValue.operator === 'date_threshold') {
    return [{ label: '签署日期', value: 'signing_date' }]
  }
  if (props.modelValue.operator === 'field_exists' || props.modelValue.operator === 'field_missing') {
    return riskRulePresenceFields
  }
  return []
})

function defaultCondition(operator: ConditionOperator): RiskRuleCondition {
  if (operator === 'keyword') {
    return { operator, field: 'contract_text', value: '' }
  }
  if (operator === 'regex') {
    return { operator, field: 'contract_text', pattern: '' }
  }
  if (operator === 'amount_threshold' || operator === 'date_threshold') {
    return operator === 'amount_threshold'
      ? { operator, field: 'contract_amount', comparison: 'gt', value: '' }
      : { operator, field: 'signing_date', comparison: 'gt', value: '' }
  }
  if (operator === 'field_exists' || operator === 'field_missing') {
    return { operator, field: 'payment_terms' }
  }
  if (operator === 'semantic') return { operator }
  if (operator === 'all' || operator === 'any') {
    return {
      operator,
      conditions: [{ operator: 'keyword', field: 'contract_text', value: '' }],
    }
  }
  return {
    operator: 'not',
    condition: { operator: 'keyword', field: 'contract_text', value: '' },
  }
}

function setOperator(value: string): void {
  const operator = value as ConditionOperator
  if (!operatorOptions.value.some((option) => option.value === operator)) return
  emit('update:modelValue', defaultCondition(operator))
}

function stringField(key: 'field' | 'value' | 'pattern'): string {
  const value = (props.modelValue as unknown as Record<string, unknown>)[key]
  return typeof value === 'string' ? value : ''
}

function setStringField(key: 'field' | 'value' | 'pattern', value: string | null): void {
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: value ?? '',
  } as RiskRuleCondition)
}

function setField(value: string): void {
  if (!fieldOptions.value.some((option) => option.value === value)) return
  emit('update:modelValue', {
    ...props.modelValue,
    field: value,
  } as RiskRuleCondition)
}

function comparison(): RiskRuleComparison {
  return props.modelValue.operator === 'amount_threshold' ||
    props.modelValue.operator === 'date_threshold'
    ? props.modelValue.comparison
    : 'gt'
}

function setComparison(value: string): void {
  if (
    props.modelValue.operator !== 'amount_threshold' &&
    props.modelValue.operator !== 'date_threshold'
  ) {
    return
  }
  emit('update:modelValue', {
    ...props.modelValue,
    comparison: value as RiskRuleComparison,
  })
}

function addChild(): void {
  if (
    props.depth >= 5 ||
    (props.modelValue.operator !== 'all' && props.modelValue.operator !== 'any') ||
    props.modelValue.conditions.length >= 20
  ) {
    return
  }
  emit('update:modelValue', {
    ...props.modelValue,
    conditions: [
      ...props.modelValue.conditions,
      { operator: 'keyword', field: 'contract_text', value: '' },
    ],
  })
}

function updateChild(index: number, child: RiskRuleCondition): void {
  if (props.modelValue.operator !== 'all' && props.modelValue.operator !== 'any') return
  const conditions = [...props.modelValue.conditions]
  conditions[index] = child
  emit('update:modelValue', { ...props.modelValue, conditions })
}

function removeChild(index: number): void {
  if (
    (props.modelValue.operator !== 'all' && props.modelValue.operator !== 'any') ||
    props.modelValue.conditions.length <= 1
  ) {
    return
  }
  emit('update:modelValue', {
    ...props.modelValue,
    conditions: props.modelValue.conditions.filter((_, childIndex) => childIndex !== index),
  })
}

function updateNotChild(child: RiskRuleCondition): void {
  if (props.modelValue.operator !== 'not') return
  emit('update:modelValue', { ...props.modelValue, condition: child })
}
</script>

<template>
  <div class="condition-editor">
    <div class="condition-editor-grid">
      <ElFormItem
        label="条件类型"
        required
      >
        <ElSelect
          :model-value="modelValue.operator"
          aria-label="条件类型"
          @update:model-value="setOperator"
        >
          <ElOption
            v-for="option in operatorOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </ElSelect>
      </ElFormItem>

      <ElFormItem
        v-if="!['semantic', 'all', 'any', 'not'].includes(modelValue.operator)"
        label="目标字段"
        required
      >
        <ElSelect
          :model-value="stringField('field')"
          placeholder="选择目标字段"
          aria-label="目标字段"
          @update:model-value="setField"
        >
          <ElOption
            v-for="option in fieldOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </ElSelect>
      </ElFormItem>

      <ElFormItem
        v-if="modelValue.operator === 'keyword'"
        label="关键词"
        required
      >
        <ElInput
          :model-value="stringField('value')"
          maxlength="2000"
          placeholder="例如：无限责任"
          aria-label="关键词"
          @update:model-value="setStringField('value', $event)"
        />
      </ElFormItem>

      <ElFormItem
        v-if="modelValue.operator === 'regex'"
        label="正则模式"
        required
      >
        <ElInput
          :model-value="stringField('pattern')"
          maxlength="1000"
          placeholder="输入受支持的正则模式"
          aria-label="正则模式"
          @update:model-value="setStringField('pattern', $event)"
        />
      </ElFormItem>

      <template
        v-if="modelValue.operator === 'amount_threshold' || modelValue.operator === 'date_threshold'"
      >
        <ElFormItem
          label="比较方式"
          required
        >
          <ElSelect
            :model-value="comparison()"
            aria-label="比较方式"
            @update:model-value="setComparison"
          >
            <ElOption
              label="大于"
              value="gt"
            />
            <ElOption
              label="大于等于"
              value="gte"
            />
            <ElOption
              label="小于"
              value="lt"
            />
            <ElOption
              label="小于等于"
              value="lte"
            />
            <ElOption
              label="等于"
              value="eq"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem
          :label="modelValue.operator === 'date_threshold' ? '日期阈值' : '金额阈值'"
          required
        >
          <ElDatePicker
            v-if="modelValue.operator === 'date_threshold'"
            :model-value="stringField('value')"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            aria-label="日期阈值"
            @update:model-value="setStringField('value', $event)"
          />
          <ElInput
            v-else
            :model-value="stringField('value')"
            inputmode="decimal"
            maxlength="128"
            placeholder="例如：100000.00"
            aria-label="金额阈值"
            @update:model-value="setStringField('value', $event)"
          />
        </ElFormItem>
      </template>
    </div>

    <ElAlert
      v-if="modelValue.operator === 'semantic'"
      title="语义条件由模型辅助判断"
      type="info"
      :closable="false"
      show-icon
    />

    <div
      v-if="modelValue.operator === 'all' || modelValue.operator === 'any'"
      class="condition-children"
    >
      <div
        v-for="(child, index) in children"
        :key="index"
        class="condition-child"
      >
        <RiskRuleConditionEditor
          :model-value="child"
          :engine="engine"
          :depth="depth + 1"
          @update:model-value="updateChild(index, $event)"
        />
        <ElButton
          :icon="Delete"
          circle
          plain
          type="danger"
          :disabled="children.length <= 1"
          title="删除子条件"
          aria-label="删除子条件"
          @click="removeChild(index)"
        />
      </div>
      <ElButton
        :icon="Plus"
        :disabled="depth >= 5 || children.length >= 20"
        @click="addChild"
      >
        添加子条件
      </ElButton>
    </div>

    <div
      v-if="modelValue.operator === 'not' && notChild"
      class="condition-children"
    >
      <RiskRuleConditionEditor
        :model-value="notChild"
        :engine="engine"
        :depth="depth + 1"
        @update:model-value="updateNotChild"
      />
    </div>
  </div>
</template>
