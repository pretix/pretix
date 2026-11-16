<script setup lang="ts">
import { computed, inject } from 'vue'
import Select from './input/select.vue'
import I18nInput from '@/pretix/static/pretixbase/components/i18n-input.vue'
import { StoreKey } from '../walletStore'

const store = inject(StoreKey)!

defineProps<{
	placeholderChoices: [string | null, string][];
}>()

const entry = defineModel<FieldEntry>({ required: true })

const selection = computed({
	get () {
		if (entry.value.type === 'placeholder') {
			return entry.value.content
		} else if (entry.value.type === 'custom') {
			return 'other'
		} else {
			throw Error('Unknown entry type')
		}
	},
	set (newValue) {
		if (newValue == 'other') {
			entry.value.type = 'custom'
			entry.value.content = {}
		} else {
			entry.value.type = 'placeholder'
			entry.value.content = newValue
		}
	}
})

const textContent = computed({
	get () {
		if (entry.value.type === 'placeholder') {
			return ''
		} else if (entry.value.type === 'custom') {
			return entry.value.content
		} else {
			throw Error('Unknown entry type')
		}
	},
	set (newValue) {
		entry.value.content = newValue
	}
})

</script>

<template lang="pug">
	.i18n-form-group
		Select(
			v-model="selection"
			:choices="placeholderChoices"
		)
		I18nInput(v-if="selection === 'other'" v-model="textContent" :locales="store.locales")
</template>
