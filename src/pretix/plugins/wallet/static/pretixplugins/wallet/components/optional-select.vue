<script setup lang="ts">
import { useId } from 'vue'

const props = defineProps<{
	label: string
	choices: [string, string][]
}>()
const modelValue = defineModel<string|null>();
const id = useId()
</script>

<template lang="pug">
    template(v-if="choices.length >= 1")
        label(:for="id") {{ props.label }}
        select.form-control(:id="id" v-model="modelValue")
            // TODO: persist/v-model
            option(v-for="choice in props.choices" :key="choice[0]" :value="choice[0]") {{ choice[1] }}
</template>
