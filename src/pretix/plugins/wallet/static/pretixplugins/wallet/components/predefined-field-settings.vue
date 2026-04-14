<script setup lang="ts">
const gettext = (window as any).gettext;

const props = defineProps<{
	fieldgroup: FieldGroupDefinition;
}>();
const fieldConfig = defineModel<PredefinedFieldGroupConfig>({ required: true });

</script>

<template lang="pug">
    .panel.panel-default
        .panel-heading
            h3.panel-title {{ fieldgroup.name }}
        .panel-body
            .form-group
                span.text-muted These fields appear somewhere and are visible too.
</template>
