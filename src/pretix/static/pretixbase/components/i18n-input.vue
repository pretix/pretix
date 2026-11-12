<script setup lang="ts">
import { watchEffect } from "vue";

defineOptions({
    inheritAttrs: false,
});

const props = defineProps<{
    placeholders: Record<string, string>;
    locales: Record<string, string>;
    errors?: string[];
    multiline?: boolean;
}>();

const modelValue = defineModel<Record<string, string> | string>();
watchEffect(() => {
    if (typeof modelValue.value === "string") {
        const oldVal = modelValue.value;
        modelValue.value = Object.fromEntries(
            Object.keys(props.locales).map((x): [string, string] => [x, oldVal]),
        );
    }
    if (modelValue.value === null) {
        modelValue.value = {};
    }
});
</script>

<template lang="pug">
    component.form-control(
        :is="multiline ? 'textarea' : 'input'"
        v-if="!!modelValue"
        v-for="(human_readable, locale) in locales"
        v-model="modelValue[locale]"
        v-bind="$attrs"
        :lang="locale"
        :title="human_readable"
        :placeholder="placeholders?.[locale] || human_readable")
    .help-block(v-if="!!errors" v-for="error in errors") {{ error }}
</template>
