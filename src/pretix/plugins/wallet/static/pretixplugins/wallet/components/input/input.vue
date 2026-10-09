<script setup lang="ts">
import { useId, computed, onMounted, useTemplateRef, onUnmounted, onUpdated, onBeforeUpdate } from "vue";

const gettext = (window as any).gettext;

defineOptions({
	inheritAttrs: false,
});

const {
	label,
	errors,
	type = "text",
	min=null,
	max=null,
	defaultVal=null
} = defineProps<{
	label?: string;
	errors?: string[];
	type?: string;
	help_text?: string;
	inline?: boolean;
	min?: number;
	max?: number;
	defaultVal?: string;
}>();
const modelValue = defineModel<string | null>();
const id = useId();
const inputRef = useTemplateRef("input");

const attrs = computed(() => {
	if (type === "float") {
		return { class: "appear-text", type: "number", step: "any", min, max };
	} else {
		return { type: "text" };
	}
});

onMounted(() => {
	if (type == "color") {
		const jq_elem = $(inputRef.value)
		jq_elem.colorpicker({
			format: "hex",
			align: "left",
			customClass: "colorpicker-2x",
			sliders: {
				saturation: {
					maxLeft: 200,
					maxTop: 200,
				},
				hue: {
					maxTop: 200,
				},
				alpha: {
					maxTop: 200,
				},
			},
		})
		jq_elem.on('changeColor', (e) => e.value && (modelValue.value = e.value))
		jq_elem.on('showPicker', () => {jq_elem.colorpicker('setValue', modelValue.value || defaultVal)});
	}
});

onUnmounted(() => {
	if (type == "color") {
		$(inputRef.value).colorpicker("destroy");
	}
});
</script>

<template lang="pug">
.form-group(:class="{'row':inline}")
    label.control-label(:for="id" v-if="label" :class="{'col-md-3': inline}") {{ label }}
        br(v-if="!$attrs.required")
        span.optional(v-if="!$attrs.required")  {{ gettext("Optional") }}
    div(:class="{'col-md-9': inline}")
        input.form-control(:id="id" ref="input" v-model="modelValue" v-bind="{...$attrs, ...attrs}")
        .help-block(v-if="!!help_text") {{ help_text }}
        .help-block(v-if="!!errors" v-for="error in errors") {{ error }}
</template>

<style lang="css" scoped>
.appear-text {
	appearance: textfield;
}
</style>
