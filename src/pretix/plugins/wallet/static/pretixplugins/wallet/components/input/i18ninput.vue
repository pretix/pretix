<script setup lang="ts">
import { useId, watchEffect } from 'vue'

defineOptions({
  inheritAttrs: false
})

const props = defineProps<{
	label?: string,
    errors?: string[],
    locales: Record<string, string>
}>()
const modelValue = defineModel<Record<string, string> | string>();
watchEffect(() => {
    if (typeof modelValue.value === "string") {
        const oldVal = modelValue.value;
        modelValue.value = Object.fromEntries(Object.keys(props.locales).map((x): [string, string] => [x, oldVal]))
    }
})
const id = useId()
</script>

<template lang="pug">
    label.control-label(:for="id", v-if="props.label") {{ props.label }}
    .i18n-form-group
        input.form-control(v-for="(human_readable, locale) in locales" v-model="modelValue[locale]" v-bind="$attrs" :lang="locale" :title="human_readable" :placeholder="human_readable")
    .help-block(v-if="props.errors" v-for="error in props.errors") {{ error }}
</template>
