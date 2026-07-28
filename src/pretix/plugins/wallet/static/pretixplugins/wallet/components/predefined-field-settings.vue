<script setup lang="ts">
import { watchEffect } from 'vue';
import Input from './input/input.vue';
import Checkbox from './input/checkbox.vue';

const gettext = (window as any).gettext;

const props = defineProps<{
	fieldgroup: FieldGroupDefinition;
}>();
const fieldConfig = defineModel<PredefinedFieldGroupConfig>({ required: true });

watchEffect(() => {
    if (!fieldConfig.value) {
        fieldConfig.value = {active: props.fieldgroup.required};
    }
});
</script>

<template lang="pug">
    .panel.panel-default.walletsettings-panel
        .panel-heading
            h3.panel-title.form-inline
                .form-group
                    Checkbox(:label="fieldgroup.name" v-model="fieldConfig.active")
        .panel-body(v-if="!!fieldgroup.description")
            .form-group
                span.text-muted {{ fieldgroup.description }}
</template>
