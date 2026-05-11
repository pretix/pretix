<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { timeFormat, datetimeLocale } from '../i18n'

const props = defineProps<{
	required?: boolean
	modelValue?: string
	id?: string
}>()

const emit = defineEmits<{
	'update:modelValue': [value: string]
}>()

const input = ref<HTMLInputElement>()

const opts = {
	format: timeFormat,
	locale: datetimeLocale,
	useCurrent: false,
	showClear: props.required,
	icons: {
		time: 'fa fa-clock-o',
		date: 'fa fa-calendar',
		up: 'fa fa-chevron-up',
		down: 'fa fa-chevron-down',
		previous: 'fa fa-chevron-left',
		next: 'fa fa-chevron-right',
		today: 'fa fa-screenshot',
		clear: 'fa fa-trash',
		close: 'fa fa-remove',
	},
}

watch(() => props.modelValue, (val) => {
	if (val) {
		$(input.value!).data('DateTimePicker').date(moment(val))
	}
})

onMounted(() => {
	$(input.value!)
		.datetimepicker(opts)
		.trigger('change')
		.on('dp.change', function (this: HTMLElement) {
			emit('update:modelValue', $(this).data('DateTimePicker').date().format('HH:mm:ss'))
		})

	if (!props.modelValue) {
		$(input.value!).data('DateTimePicker').viewDate(moment().hour(0).minute(0).second(0).millisecond(0))
	} else {
		$(input.value!).data('DateTimePicker').date(moment(props.modelValue))
	}
})

onUnmounted(() => {
	$(input.value!)
		.off()
		.datetimepicker('destroy')
})
</script>
<template lang="pug">
input.form-control(:id="id", ref="input", :required="required")
</template>
