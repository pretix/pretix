<script setup lang="ts">
import { computed } from 'vue'
import { TEXTS } from './constants'
import { rules } from './django-interop'
import CheckinRule from './checkin-rule.vue'

const hasRules = computed(() => !!Object.keys(rules.value).length)

function addRule () {
	rules.value.and = []
}
</script>
<template lang="pug">
.checkin-rules-editor
	CheckinRule(v-if="hasRules", :rule="rules", :level="0", :index="0")
	button.checkin-rule-addchild.btn.btn-xs.btn-default(
		v-if="!hasRules",
		type="button",
		@click.prevent="addRule"
	)
		span.fa.fa-plus-circle
		| {{ TEXTS.condition_add }}
</template>
