<script setup lang="ts">
import { inject, watchEffect } from 'vue'
import { StoreKey } from "../../walletStore";

const store = inject(StoreKey)!

defineOptions({
  inheritAttrs: false
})

const props = defineProps<{
    errors?: string[],
    placeholders: Record<string, string>
}>();

const modelValue = defineModel<Record<string, string> | string>();
watchEffect(() => {
    if (typeof modelValue.value === "string") {
        const oldVal = modelValue.value;
        modelValue.value = Object.fromEntries(Object.keys(store.locales).map((x): [string, string] => [x, oldVal]))
    }
    if (modelValue.value === null) {
        modelValue.value = {};
    }
})
</script>

<template lang="pug">
    input.form-control(v-if="!!modelValue" v-for="(human_readable, locale) in store.locales" v-model="modelValue[locale]" v-bind="$attrs" :lang="locale" :title="human_readable" :placeholder="placeholders[locale] || human_readable")
    .help-block(v-if="!!errors" v-for="error in errors") {{ error }}
</template>
