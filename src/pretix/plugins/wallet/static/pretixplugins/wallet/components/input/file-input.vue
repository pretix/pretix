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
    default?: string;
}>();
const id = useId();

const selectedFile = ref(null);
function onChange(e) {
    selectedFile.value = (e.target as HTMLInputElement).files[0] || null
    emit("change", selectedFile.value)
}

// Reset input field if a url is provided
const inputRef = ref<HTMLInputElement>();
watchEffect(() => {
    if (props.current_url && inputRef.value?.value) {
        inputRef.value.value = '';
    }
})

const clearFile = () => {
    if (!inputRef.value) {
        return
    }
    var event = new Event('change');
    inputRef.value.value = '';
    inputRef.value.dispatchEvent(event)
}
</script>

<template lang="pug">
.form-group.row
    label.control-label.col-md-3(:for="id", v-if="!!label") {{ label }}
        br(v-if="!$attrs.required")
        span.optional(v-if="!$attrs.required")  {{ gettext("Optional") }}

    div.col-md-9
        template(v-if="!!current_url")
            | {{  gettext("Currently") + ': ' }}
            a(:href="current_url" data-lightbox="input") {{ filename }}
            | {{ " " }}
            button.btn.btn-sm(@click.prevent="() => {console.log('clear'); emit('change', null)}") {{ gettext("Clear") }}
            br
            | {{ gettext("Change") + ': ' }}
        input(:id="id" @change="onChange" v-bind="$attrs" :required="$attrs.required && !current_url" type="file" style="display: inline" ref="inputRef")
        | {{ " " }}
        button.btn.btn-sm(v-if="selectedFile" @click.prevent="clearFile") {{ gettext("Clear") }}
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
