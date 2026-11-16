<script setup lang="ts">
import { computed, ref, useId } from 'vue'

const gettext = (window as any).gettext

const selectedFile = defineModel<{ name: string; url: string; }>()

const props = defineProps<{
	label?: LocalizableString;
	errors?: string[];
	helpText?: string;
	default?: string;
}>()
const id = useId()

function onChange (e) {
	selectedFile.value = (e.target as HTMLInputElement).files[0] || null
}
const inputRef = ref<HTMLInputElement>()

function clearFile () {
	selectedFile.value = null
}

function onDrop (e) {
	selectedFile.value = e.dataTransfer.files[0] || null
}

const hasFile = computed(() => {
	return !!selectedFile.value?.name
})
</script>

<template lang="pug">
.form-group.row
	label.control-label.col-md-3(v-if="!!label", :for="id") {{ label }}
		br(v-if="!$attrs.required")
		span.optional(v-if="!$attrs.required")  {{ gettext("Optional") }}

	div.col-md-9(@drop.stop.prevent="onDrop" @dragover.stop.prevent @dragenter.stop.prevent)
		div(v-if="hasFile")
			| {{ gettext("Currently") + ': ' }}
			a(:href="selectedFile.url" data-lightbox="input") {{ selectedFile.name }}

		.btn-group
			button.btn.btn-default(type="button" @click="inputRef.click()") Select file
			button.btn.btn-danger(v-if="hasFile" type="button" @click="clearFile")
				i.fa.fa-trash
				span.sr-only {{ gettext("Clear") }}
		input.hidden(:id="id" v-bind="$attrs" ref="inputRef" :required="!!$attrs.required" type="file" @change="onChange")
		.help-block(v-if="!!helpText || !!props.default")
			template(v-if="!!helpText") {{ helpText }}
			br(v-if="!!helpText && !!props.default")
			template(v-if="!!props.default")
				a(:href="props.default" data-lightbox="input") {{ gettext("Show default") }}

		template(v-if="!!errors")
			.help-block(v-for="error in errors") {{ error }}
</template>

<style lang="css" scoped>
.thumb-img {
	max-height: 100px;
	max-width: 200px;
	object-fit: contain;
}
</style>
