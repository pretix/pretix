<script setup lang="ts">
import { useId } from "vue";

const gettext = (window as any).gettext;

defineOptions({
	inheritAttrs: false,
});

const {
	label,
	errors,
} = defineProps<{
	label?: I18nString;
	errors?: string[];
	help_text?: string;
}>();
const modelValue = defineModel<string | File | null>();
const id = useId();
function onChange(e) {
    modelValue.value = (e.target as HTMLInputElement).files[0]
}
</script>

<template lang="pug">
.form-group.row
    label.control-label.col-md-3(:for="id", v-if="!!label") {{ label }}
        br(v-if="!$attrs.required")
        span.optional(v-if="!$attrs.required")  {{ gettext("Optional") }}
    div.col-md-9
        template(v-if="typeof modelValue == 'string'")
            | {{  gettext("Currently") + ': ' }}
            //- TODO: preview filename
            a(:href="modelValue") FILENAME
            | {{ " " }}
            button.btn.btn-sm(@click.prevent="() => {console.log('clear'); modelValue = null}") {{ gettext("Clear") }}
            //- br
            //- a(:href="modelValue" data-lightbox="input")
            //-     img.thumb-img(:src="modelValue")
            br
            | {{ gettext("Change") + ': ' }}
        input(:id="id" @change="onChange" v-bind="$attrs" type="file" style="display: inline")
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
