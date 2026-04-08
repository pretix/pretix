<script setup lang="ts">
import { computed, watchEffect } from "vue";
import FieldSettings from "./field-settings.vue";

const gettext = (window as any).gettext;

const props = defineProps<{
	styles: Styles;
	variables: VariableConfig
	style?: string;
}>();

const layout = defineModel<LayoutData>();

const styleData = computed(() => {
	if (!props.style || !(props.style in props.styles)) {
		return null;
	}
	return props.styles[props.style];
});

watchEffect(() => {
	// TODO: this seems wrooong
	if (!("fields" in layout.value)) {
		layout.value.fields = {};
	}
	if (props.style) {
		for (const field of props.styles[props.style].fields) {
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
    FieldSettings(v-if="styleData"
                  v-for="(field, fieldId) in styleData.fields"
                  v-model="layout.fields[field.identifier]"
                  :field="field"
                  :overflows="styleData.fields.slice(fieldId + 1).filter(x => x.entry_type === field.entry_type)"
                  :variables="variables[field.entry_type]"
                )
</template>
