<script setup lang="ts">
/* eslint-disable vue/no-mutating-props */
import { computed } from 'vue'
import { TEXTS, VARS, TYPEOPS } from './constants'
import { productSelectURL, variationSelectURL, gateSelectURL } from './django-interop'
import LookupSelect2 from './lookup-select2.vue'
import Datetimefield from './datetimefield.vue'
import Timefield from './timefield.vue'

const props = defineProps<{
	rule: any
	level: number
	index: number
}>()

const emit = defineEmits<{
	remove: []
	duplicate: []
}>()

const operator = computed(() => Object.keys(props.rule)[0])
const operands = computed(() => props.rule[operator.value])

const variable = computed(() => {
	const op = operator.value
	if (op === 'and' || op === 'or') {
		return op
	} else if (props.rule[op]?.[0]) {
		if (props.rule[op][0]['entries_since']) return 'entries_since'
		if (props.rule[op][0]['entries_before']) return 'entries_before'
		if (props.rule[op][0]['entries_days_since']) return 'entries_days_since'
		if (props.rule[op][0]['entries_days_before']) return 'entries_days_before'
		return props.rule[op][0]['var']
	}
	return null
})

const rightoperand = computed(() => {
	const op = operator.value
	if (op === 'and' || op === 'or') return null
	return props.rule[op]?.[1] ?? null
})

const classObject = computed(() => ({
	'checkin-rule': true,
	['checkin-rule-' + variable.value]: true
}))

const vartype = computed(() => VARS[variable.value]?.type)

const timeType = computed(() => {
	if (vartype.value === 'int_by_datetime') {
		return props.rule[operator.value]?.[0]?.[variable.value]?.[0]?.buildTime?.[0]
	}
	return rightoperand.value?.buildTime?.[0]
})

const timeTolerance = computed(() => {
	const op = operator.value
	if ((op === 'isBefore' || op === 'isAfter') && props.rule[op]?.[2] !== undefined) {
		return props.rule[op][2]
	}
	return null
})

const timeValue = computed(() => {
	if (vartype.value === 'int_by_datetime') {
		return props.rule[operator.value]?.[0]?.[variable.value]?.[0]?.buildTime?.[1]
	}
	return rightoperand.value?.buildTime?.[1]
})

const cardinality = computed(() => TYPEOPS[vartype.value]?.[operator.value]?.cardinality)
const operators = computed(() => TYPEOPS[vartype.value])

function setVariable (event: Event) {
	const target = event.target as HTMLSelectElement
	const currentOp = Object.keys(props.rule)[0]
	let currentVal = props.rule[currentOp]

	if (target.value === 'and' || target.value === 'or') {
		if (currentVal[0]?.var) currentVal = []
		props.rule[target.value] = currentVal
		delete props.rule[currentOp]
	} else {
		if (currentVal !== 'and' && currentVal !== 'or' && currentVal[0] && VARS[target.value]?.type === vartype.value) {
			if (vartype.value === 'int_by_datetime') {
				const currentData = props.rule[currentOp][0][variable.value]
				props.rule[currentOp][0] = { [target.value]: JSON.parse(JSON.stringify(currentData)) }
			} else {
				props.rule[currentOp][0].var = target.value
			}
		} else if (VARS[target.value]?.type === 'int_by_datetime') {
			delete props.rule[currentOp]
			props.rule['!!'] = [{ [target.value]: [{ buildTime: [null, null] }] }]
		} else {
			delete props.rule[currentOp]
			props.rule['!!'] = [{ var: target.value }]
		}
	}
}

function setOperator (event: Event) {
	const target = event.target as HTMLSelectElement
	const currentOp = Object.keys(props.rule)[0]
	const currentVal = props.rule[currentOp]
	delete props.rule[currentOp]
	props.rule[target.value] = currentVal
}

function setRightOperandNumber (event: Event) {
	const val = parseInt((event.target as HTMLInputElement).value)
	if (props.rule[operator.value].length === 1) {
		props.rule[operator.value].push(val)
	} else {
		props.rule[operator.value][1] = val
	}
}

function setTimeTolerance (event: Event) {
	const val = parseInt((event.target as HTMLInputElement).value)
	if (props.rule[operator.value].length === 2) {
		props.rule[operator.value].push(val)
	} else {
		props.rule[operator.value][2] = val
	}
}

function setTimeType (event: Event) {
	const val = (event.target as HTMLSelectElement).value
	const time = { buildTime: [val] }
	if (vartype.value === 'int_by_datetime') {
		props.rule[operator.value][0][variable.value][0] = time
	} else {
		if (props.rule[operator.value].length === 1) {
			props.rule[operator.value].push(time)
		} else {
			props.rule[operator.value][1] = time
		}
		if (val === 'custom') {
			props.rule[operator.value][2] = 0
		}
	}
}

function setTimeValue (val: string) {
	if (vartype.value === 'int_by_datetime') {
		props.rule[operator.value][0][variable.value][0]['buildTime'][1] = val
	} else {
		props.rule[operator.value][1]['buildTime'][1] = val
	}
}

function setRightOperandProductList (val: { id: any; text: string }[]) {
	const products = { objectList: val.map(item => ({ lookup: ['product', item.id, item.text] })) }
	if (props.rule[operator.value].length === 1) {
		props.rule[operator.value].push(products)
	} else {
		props.rule[operator.value][1] = products
	}
}

function setRightOperandVariationList (val: { id: any; text: string }[]) {
	const products = { objectList: val.map(item => ({ lookup: ['variation', item.id, item.text] })) }
	if (props.rule[operator.value].length === 1) {
		props.rule[operator.value].push(products)
	} else {
		props.rule[operator.value][1] = products
	}
}

function setRightOperandGateList (val: { id: any; text: string }[]) {
	const products = { objectList: val.map(item => ({ lookup: ['gate', item.id, item.text] })) }
	if (props.rule[operator.value].length === 1) {
		props.rule[operator.value].push(products)
	} else {
		props.rule[operator.value][1] = products
	}
}

function setRightOperandEnum (event: Event) {
	const val = (event.target as HTMLSelectElement).value
	if (props.rule[operator.value].length === 1) {
		props.rule[operator.value].push(val)
	} else {
		props.rule[operator.value][1] = val
	}
}

function addOperand () {
	props.rule[operator.value].push({ '': [] })
}

function wrapWithOR () {
	const r = JSON.parse(JSON.stringify(props.rule))
	delete props.rule[operator.value]
	props.rule.or = [r]
}

function wrapWithAND () {
	const r = JSON.parse(JSON.stringify(props.rule))
	delete props.rule[operator.value]
	props.rule.and = [r]
}

function cutOut () {
	const cop = Object.keys(operands.value[0])[0]
	const r = operands.value[0][cop]
	delete props.rule[operator.value]
	props.rule[cop] = r
}

function remove () {
	emit('remove')
}

function duplicate () {
	emit('duplicate')
}

function removeChild (index: number) {
	props.rule[operator.value].splice(index, 1)
}

function duplicateChild (index: number) {
	const r = JSON.parse(JSON.stringify(props.rule[operator.value][index]))
	props.rule[operator.value].splice(index, 0, r)
}
</script>
<template lang="pug">
div(:class="classObject")
	.btn-group.pull-right
		button.checkin-rule-remove.btn.btn-xs.btn-default(
			v-if="level > 0",
			type="button",
			data-toggle="tooltip",
			:title="TEXTS.duplicate",
			@click.prevent="duplicate"
		)
			span.fa.fa-copy
		button.checkin-rule-remove.btn.btn-xs.btn-default(
			type="button",
			@click.prevent="wrapWithOR"
		) OR
		button.checkin-rule-remove.btn.btn-xs.btn-default(
			type="button",
			@click.prevent="wrapWithAND"
		) AND
		button.checkin-rule-remove.btn.btn-xs.btn-default(
			v-if="operands && operands.length === 1 && (operator === 'or' || operator === 'and')",
			type="button",
			@click.prevent="cutOut"
		)
			span.fa.fa-cut
		button.checkin-rule-remove.btn.btn-xs.btn-default(
			v-if="level > 0",
			type="button",
			@click.prevent="remove"
		)
			span.fa.fa-trash
	select.form-control(:value="variable", required, @input="setVariable")
		option(value="and") {{ TEXTS.and }}
		option(value="or") {{ TEXTS.or }}
		option(v-for="(v, name) in VARS", :key="name", :value="name") {{ v.label }}
	select.form-control(
		v-if="operator !== 'or' && operator !== 'and' && vartype !== 'int_by_datetime'",
		:value="operator",
		required,
		@input="setOperator"
	)
		option
		option(v-for="(v, name) in operators", :key="name", :value="name") {{ v.label }}
	select.form-control(
		v-if="vartype === 'datetime' || vartype === 'int_by_datetime'",
		:value="timeType",
		required,
		@input="setTimeType"
	)
		option(value="date_from") {{ TEXTS.date_from }}
		option(value="date_to") {{ TEXTS.date_to }}
		option(value="date_admission") {{ TEXTS.date_admission }}
		option(value="custom") {{ TEXTS.date_custom }}
		option(value="customtime") {{ TEXTS.date_customtime }}
	Datetimefield(
		v-if="(vartype === 'datetime' || vartype === 'int_by_datetime') && timeType === 'custom'",
		:value="timeValue",
		@input="setTimeValue"
	)
	Timefield(
		v-if="(vartype === 'datetime' || vartype === 'int_by_datetime') && timeType === 'customtime'",
		:value="timeValue",
		@input="setTimeValue"
	)
	input.form-control(
		v-if="vartype === 'datetime' && timeType && timeType !== 'customtime' && timeType !== 'custom'",
		required,
		type="number",
		:value="timeTolerance",
		:placeholder="TEXTS.date_tolerance",
		@input="setTimeTolerance"
	)
	select.form-control(
		v-if="vartype === 'int_by_datetime'",
		:value="operator",
		required,
		@input="setOperator"
	)
		option
		option(v-for="(v, name) in operators", :key="name", :value="name") {{ v.label }}
	input.form-control(
		v-if="(vartype === 'int' || vartype === 'int_by_datetime') && cardinality > 1",
		required,
		type="number",
		:value="rightoperand",
		@input="setRightOperandNumber"
	)
	LookupSelect2(
		v-if="vartype === 'product' && operator === 'inList'",
		required,
		:multiple="true",
		:value="rightoperand",
		:url="productSelectURL",
		@input="setRightOperandProductList"
	)
	LookupSelect2(
		v-if="vartype === 'variation' && operator === 'inList'",
		required,
		:multiple="true",
		:value="rightoperand",
		:url="variationSelectURL",
		@input="setRightOperandVariationList"
	)
	LookupSelect2(
		v-if="vartype === 'gate' && operator === 'inList'",
		required,
		:multiple="true",
		:value="rightoperand",
		:url="gateSelectURL",
		@input="setRightOperandGateList"
	)
	select.form-control(
		v-if="vartype === 'enum_entry_status' && operator === '=='",
		required,
		:value="rightoperand",
		@input="setRightOperandEnum"
	)
		option(value="absent") {{ TEXTS.status_absent }}
		option(value="present") {{ TEXTS.status_present }}
	.checkin-rule-childrules(v-if="operator === 'or' || operator === 'and'")
		div(v-for="(op, opi) in operands", :key="opi")
			CheckinRule(
				v-if="typeof op === 'object'",
				:rule="op",
				:index="opi",
				:level="level + 1",
				@remove="removeChild(opi)",
				@duplicate="duplicateChild(opi)"
			)
		button.checkin-rule-addchild.btn.btn-xs.btn-default(
			type="button",
			@click.prevent="addOperand"
		)
			span.fa.fa-plus-circle
			| {{ TEXTS.condition_add }}
</template>
