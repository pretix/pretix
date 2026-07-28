<script setup lang="ts">
import { useId } from 'vue'

defineOptions({
  inheritAttrs: false
})

const props = defineProps<{
	label?: string
}>()
const modelValue = defineModel<boolean|null>();
const id = useId()
</script>

<template lang="pug">
    .checkbox
        label
            input(:id="id" v-model="modelValue" v-bind="$attrs" type="checkbox")
            | {{ props.label }}
</template>
