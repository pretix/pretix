<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'

declare const $: any

export interface ObjectListItem {
	lookup: [string, number | string, string]
}

export interface ObjectList {
	objectList: ObjectListItem[]
}

const props = defineProps<{
	required?: boolean
	value?: ObjectList
	placeholder?: string
	url?: string
	multiple?: boolean
}>()

const emit = defineEmits<{
	input: [value: any[]]
}>()

const select = ref<HTMLSelectElement | null>(null)

function opts () {
	return {
		theme: 'bootstrap',
		delay: 100,
		width: '100%',
		multiple: true,
		allowClear: props.required,
		language: $('body').attr('data-select2-locale'),
		ajax: {
			url: props.url,
			data: function (params: { term: string; page?: number }) {
				return {
					query: params.term,
					page: params.page || 1
				}
			}
		},
		templateResult: function (res: { id?: string; text: string }) {
			if (!res.id) {
				return res.text
			}
			const $ret = $('<span>').append(
				$('<span>').addClass('primary').append($('<div>').text(res.text).html())
			)
			return $ret
		},
	}
}

function build () {
	$(select.value)
		.empty()
		.select2(opts())
		.val(props.value || '')
		.trigger('change')
		.on('change', function (this: HTMLElement) {
			emit('input', $(this).select2('data'))
		})
	if (props.value) {
		for (let i = 0; i < props.value.objectList.length; i++) {
			const option = new Option(props.value.objectList[i].lookup[2], String(props.value.objectList[i].lookup[1]), true, true)
			$(select.value).append(option)
		}
	}
	$(select.value).trigger('change')
}

watch(() => props.placeholder, () => {
	$(select.value).select2('destroy')
	build()
})

watch(() => props.required, () => {
	$(select.value).select2('destroy')
	build()
})

watch(() => props.url, () => {
	$(select.value).select2('destroy')
	build()
})

watch(() => props.value, (newval, oldval) => {
	if (JSON.stringify(newval) !== JSON.stringify(oldval)) {
		$(select.value).empty()
		if (newval) {
			for (let i = 0; i < newval.objectList.length; i++) {
				const option = new Option(newval.objectList[i].lookup[2], String(newval.objectList[i].lookup[1]), true, true)
				$(select.value).append(option)
			}
		}
		$(select.value).trigger('change')
	}
})

onMounted(() => {
	build()
})

onUnmounted(() => {
	$(select.value)
		.off()
		.select2('destroy')
})
</script>
<template lang="pug">
select(ref="select")
	slot
</template>
