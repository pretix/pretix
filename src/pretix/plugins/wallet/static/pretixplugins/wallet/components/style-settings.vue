<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import OptionalSelect from './optional-select.vue'
import FieldSettings from './field-settings.vue'

const props = defineProps<{
	styles: any, // TODO
	variables: any, // TODO
	style?: string,
}>()

const layout = defineModel()

const styleData = computed(() => {
	if (!props.style || !(props.style in props.styles)) {
		return null
	}
	return props.styles[props.style]
})

watchEffect(() => {
	// TODO: this seems wrooong
    if (!('fields' in layout.value)) {
        layout.value.fields = {}
    }
	if (props.style) {
		for (const field of props.styles[props.style].fields) {
			if (!(field.identifier in layout.value.fields)) {
				layout.value.fields[field.identifier] = {entries: JSON.parse(JSON.stringify(field.default_entries)), overflow: null}
			}
		}
	}
})
</script>

<template lang="pug">
    h2.h3 Form Fields
    FieldSettings(v-if="styleData"
                  v-for="(field, fieldId) in styleData.fields"
                  v-model="layout.fields[field.identifier]"
                  :field="field"
                  :overflows="styleData.fields.slice(fieldId+1).filter(x => x.entry_type === field.entry_type)"
                  :variables="variables"
                )
</template>
