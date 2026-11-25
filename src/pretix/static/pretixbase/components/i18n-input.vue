<script setup lang="ts">
import { watchEffect } from 'vue'

defineOptions({
	inheritAttrs: false,
})

const props = defineProps<{
	placeholders?: Record<string, string>;
	locales: Record<string, string>;
	errors?: string[];
	multiline?: boolean;
}>()

const modelValue = defineModel<Record<string, string> | string>({ default: () => ({}) })

watchEffect(() => {
	if (typeof modelValue.value === 'string') {
		const oldVal = modelValue.value
		modelValue.value = Object.fromEntries(
			Object.keys(props.locales).map((x): [string, string] => [x, oldVal]),
		)
	}

	const additionalLocales = new Set(Object.keys(modelValue.value)).difference(new Set(Object.keys(props.locales)))
	for (const additionalLocale of additionalLocales) {
		delete modelValue.value[additionalLocale]
	}
})
</script>

<template lang="pug">
    template(v-if="!!modelValue")
        div.i18n-form-group
            component.form-control(
                :is="multiline ? 'textarea' : 'input'"
                v-for="(human_readable, locale) in locales"
                v-bind="$attrs"
                :key="locale"
                :lang="locale"
                :title="human_readable"
                :placeholder="placeholders?.[locale] || human_readable"
                :value="modelValue[locale]"
                @input="event => modelValue[locale] = event.target.value"
            )
        template(v-if="!!errors")
            .help-block(v-for="error in errors") {{ error }}
</template>
