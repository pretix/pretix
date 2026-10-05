<script setup lang="ts">
import { useId } from 'vue'

const gettext = (window as any).gettext;

defineOptions({
  inheritAttrs: false
})

const {label, errors, type = "text"} = defineProps<{
	label?: I18nString,
    errors?: string[],
    type?: string
    help_text?: string,
    inline?: boolean
}>()
const modelValue = defineModel<string|null>();
const id = useId()
</script>

<template lang="pug">
.form-group(:class="{'row':inline}")
    label.control-label(:for="id" v-if="label" :class="{'col-md-3': inline}") {{ label }}
        br(v-if="!$attrs.required")
        span.optional(v-if="!$attrs.required")  {{ gettext("Optional") }}
    div(:class="{'col-md-9': inline}")
        input(:id="id" v-model="modelValue" v-bind="$attrs" :type="type" :class="{'form-control': type == 'text'}")
        .help-block(v-if="!!help_text") {{ help_text }}
        .help-block(v-if="!!errors" v-for="error in errors") {{ error }}
</template>
