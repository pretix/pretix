<script setup lang="ts">
import { computed, watchEffect } from "vue";
import FieldSettings from "./field-settings.vue";

const gettext = (window as any).gettext;

const props = defineProps<{
	variables: VariableConfig
	style?: Style;
}>();

const layout = defineModel<LayoutData>();


watchEffect(() => {
	if (layout.value === undefined) {
		return
	}
	if (layout.value.fields === undefined) {
		layout.value.fields = {};
	}
	if (props.style) {
		for (const field of props.style.fields) {
			if (!(field.identifier in layout.value.fields)) {
				layout.value.fields[field.identifier] = {
					entries: JSON.parse(JSON.stringify(field.default_entries)),
					overflow: null,
				};
			}
		}
	}
});
</script>

<template lang="pug">
    h2.h3 {{ gettext("Field Groups") }}
    FieldSettings(v-if="props.style"
                  v-for="(field, fieldId) in props.style.fields"
                  v-model="layout.fields[field.identifier]"
                  :field="field"
                  :overflows="props.style.fields.slice(fieldId + 1).filter(x => x.entry_type === field.entry_type)"
                  :variables="variables[field.entry_type]"
                )
</template>
