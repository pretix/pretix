<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { DATETIME_OPTIONS } from './constants'

const props = defineProps<{
	required?: boolean
	value?: string
}>()

const emit = defineEmits<{
	input: [value: string]
}>()

const input = ref<HTMLInputElement | null>(null)

watch(() => props.value, (val) => {
	$(input.value).data('DateTimePicker').date(val)
})

onMounted(() => {
	$(input.value)
		.datetimepicker({
			...DATETIME_OPTIONS,
			showClear: props.required,
		})
		.trigger('change')
		.on('dp.change', function (this: HTMLElement) {
			emit('input', $(this).data('DateTimePicker').date().format('HH:mm:ss'))
		})
	if (!props.value) {
		$(input.value).data('DateTimePicker').viewDate(moment().hour(0).minute(0).second(0).millisecond(0))
	} else {
		$(input.value).data('DateTimePicker').date(props.value)
	}
})

onUnmounted(() => {
	$(input.value)
		.off()
		.datetimepicker('destroy')
})
</script>
<template lang="pug">
input.form-control(ref="input")
</template>
