<script setup lang="ts">
import { ref, useId, watchEffect } from "vue";

const gettext = (window as any).gettext;

defineOptions({
	inheritAttrs: false,
});
const emit = defineEmits<{change: [File]}>()
const props = defineProps<{
	label?: I18nString;
	errors?: string[];
	help_text?: string;
    filename?: string;
    current_url?: string;
}>();
const id = useId();
function onChange(e) {
    emit("change", (e.target as HTMLInputElement).files[0])
}

// Reset input field if a url is provided
const inputRef = ref<HTMLInputElement>();
watchEffect(() => {
    if (props.current_url && inputRef.value?.value) {
        inputRef.value.value = '';
    }
})
</script>

<template lang="pug">
.form-group.row
    label.control-label.col-md-3(:for="id", v-if="!!label") {{ label }}
        br(v-if="!$attrs.required")
        span.optional(v-if="!$attrs.required")  {{ gettext("Optional") }}
    div.col-md-9
        template(v-if="!!current_url")
            | {{  gettext("Currently") + ': ' }}
            a(:href="current_url") {{ filename }}
            | {{ " " }}
            button.btn.btn-sm(@click.prevent="() => {console.log('clear'); emit('change', null)}") {{ gettext("Clear") }}
            //- br
            //- a(:href="modelValue" data-lightbox="input")
            //-     img.thumb-img(:src="modelValue")
            br
            | {{ gettext("Change") + ': ' }}
        input(:id="id" @change="onChange" v-bind="$attrs" type="file" style="display: inline" ref="inputRef")
        .help-block(v-if="!!help_text") {{ help_text }}
        .help-block(v-if="!!errors" v-for="error in errors") {{ error }}
</template>

<style lang="css" scoped>
.thumb-img {
	max-height: 100px;
	max-width: 200px;
    object-fit: contain;
}
</style>
