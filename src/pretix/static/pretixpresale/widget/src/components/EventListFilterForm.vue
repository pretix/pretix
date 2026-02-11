<script setup lang="ts">
import { inject, ref } from 'vue'
import { StoreKey } from '~/sharedStore'
import { STRINGS } from '~/i18n'
import EventListFilterField from './EventListFilterField.vue'

const store = inject(StoreKey)!
const filterform = ref<HTMLFormElement>()

function onSubmit(e: Event) {
	e.preventDefault()
	if (!filterform.value) return

	const formData = new FormData(filterform.value)
	const filterParams = new URLSearchParams()

	formData.forEach((value, key) => {
		if (value !== '') {
			filterParams.set(key, value as string)
		}
	})

	store.filter = filterParams.toString()
	store.loading++
	store.reload()
}
</script>

<template lang="pug">
form.pretix-widget-event-list-filter-form(ref="filterform", @submit="onSubmit")
	fieldset.pretix-widget-event-list-filter-fieldset
		legend {{ STRINGS.filter_events_by }}
		EventListFilterField(
			v-for="field in store.metaFilterFields",
			:key="field.key",
			:field="field"
		)
		button {{ STRINGS.filter }}
</template>

<style lang="sass">
</style>
