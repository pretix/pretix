<script setup lang="ts">
import { useId, watchEffect } from 'vue'

defineOptions({
  inheritAttrs: false
})

const props = defineProps<{
	label: string
	choices: Array<[string, string]>
    errors?: string[]
}>()
const modelValue = defineModel<string|null>();
const id = useId()

watchEffect(() => {
    if (props.choices.length === 1) {
        modelValue.value = props.choices[0][0]
    } else if (props.choices.length < 1) {
        modelValue.value = null
    }
})
</script>

<template lang="pug">
    template(v-if="choices.length >= 1")
        label.control-label(:for="id") {{ props.label }}
        select.form-control(:id="id" v-model="modelValue" v-bind="$attrs")
            option(v-for="choice in props.choices" :key="choice[0]" :value="choice[0]") {{ choice[1] }}
        .help-block(v-if="props.errors" v-for="error in props.errors") {{ error }}
</template>
