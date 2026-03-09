<script setup lang="ts">
import { computed, inject } from 'vue'
import type { MetaFilterField } from '~/types'
import { StoreKey, globalWidgetId } from '~/sharedStore'

const props = defineProps<{
	field: MetaFilterField
}>()

const store = inject(StoreKey)!

const id = computed(() => `${globalWidgetId}_${props.field.key}`)

const currentValue = computed(() => {
	const filterParams = new URLSearchParams(store.filter || '')
	return filterParams.get(props.field.key) || ''
})
</script>
<template lang="pug">
.pretix-widget-event-list-filter-field
	label(:for="id") {{ field.label }}
	select(:id="id", :name="field.key", :value="currentValue")
		option(v-for="choice in field.choices", :key="choice[0]", :value="choice[0]") {{ choice[1] }}
</template>
<style lang="sass">
</style>
