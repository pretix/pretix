<script setup lang="ts">
import { useId, computed, onMounted, useTemplateRef, onUnmounted } from "vue";

const gettext = (window as any).gettext;

defineOptions({
	inheritAttrs: false,
});

const {
	label,
	errors,
	type = "text",
} = defineProps<{
	label?: I18nString;
	errors?: string[];
	type?: string;
	help_text?: string;
	inline?: boolean;
}>();
const modelValue = defineModel<string | null>();
const id = useId();
const inputRef = useTemplateRef("input");

const attrs = computed(() => {
	if (type === "float") {
		return { class: "appear-text", type: "number", step: "any" };
	} else {
		return { type: "text" };
	}
});

onMounted(() => {
	if (type == "color") {
		$(inputRef.value).colorpicker({
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
		}).on('changeColor', (e) => e.value && (modelValue.value = e.value));
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
