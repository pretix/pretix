<script setup lang="ts">
import { computed, ref, useId, watchEffect } from "vue";

const gettext = (window as any).gettext;

const selectedFile = defineModel<{"name": string; "url": string;}>()

const props = defineProps<{
	label?: LocalizableString;
	errors?: string[];
	help_text?: string;
    default?: string;
}>();
const id = useId();

function onChange(e) {
    selectedFile.value = (e.target as HTMLInputElement).files[0] || null
}
const inputRef = ref<HTMLInputElement>();

function clearFile() {
    selectedFile.value = null;
}

function onDrop(e) {
    selectedFile.value = e.dataTransfer.files[0] || null
}
</script>

<template lang="pug">
.form-group.row
    label.control-label.col-md-3(:for="id", v-if="!!label") {{ label }}
        br(v-if="!$attrs.required")
        span.optional(v-if="!$attrs.required")  {{ gettext("Optional") }}

    div.col-md-9(@drop.stop.prevent="onDrop" @dragover.stop.prevent @dragenter.stop.prevent)
        div(v-if="!!selectedFile")
            | {{  gettext("Currently") + ': ' }}
            a(:href="selectedFile.url" data-lightbox="input") {{ selectedFile.name }}

        .btn-group
            button.btn.btn-default(type="button" @click="inputRef.click()") Select file
            button.btn.btn-danger(v-if="!!selectedFile || !!current_url" type="button" @click="clearFile")
                i.fa.fa-trash
                span.sr-only {{ gettext("Clear") }}
        input.hidden(:id="id" @change="onChange" v-bind="$attrs" :required="$attrs.required && !current_url" type="file" ref="inputRef")
        .help-block(v-if="!!help_text || !!props.default")
            template(v-if="!!help_text") {{ help_text }}
            br(v-if="!!help_text && !!props.default")
            template(v-if="!!props.default")
                a(:href="props.default" data-lightbox="input") {{ gettext("Show default") }}

        .help-block(v-if="!!errors" v-for="error in errors") {{ error }}
</template>

<style lang="css" scoped>
.thumb-img {
	max-height: 100px;
	max-width: 200px;
    object-fit: contain;
}
</style>
