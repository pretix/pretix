<script setup lang="ts">
import { useId } from 'vue'

defineOptions({
  inheritAttrs: false
})

const props = defineProps<{
	label?: string,
    errors?: string[],
}>()
const modelValue = defineModel<string|null>();
const id = useId()
</script>

<template lang="pug">
    label.control-label(:for="id", v-if="props.label") {{ props.label }}
    input.form-control(:id="id" v-model="modelValue" v-bind="$attrs")
    .help-block(v-if="props.errors" v-for="error in props.errors") {{ error }}
</template>
