<script setup lang="ts">
import { computed, inject, watchEffect } from "vue";
import PlaceholderFieldSettings from "./placeholder-field-settings.vue";
import PredefinedFieldSettings from "./predefined-field-settings.vue";

const gettext = (window as any).gettext;

const props = defineProps<{
	style?: Style;
}>();

const layout = defineModel<LayoutData>();
</script>

<template lang="pug">
    h2.h3 {{ gettext("Field Groups") }}
    template(v-if="props.style && layout.fieldgroups"
             v-for="(fieldgroup, fieldgroupId) in props.style.fieldgroups")
        PlaceholderFieldSettings(
            v-if="fieldgroup.type == 'placeholder'"
            v-model="layout.fieldgroups[fieldgroup.identifier]"
            :fieldgroup="fieldgroup"
            :overflows="props.style.fieldgroups.slice(fieldgroupId + 1) \
                .filter(x => x.type == 'placeholder' && x.content_type === fieldgroup.content_type)"
        )
        PredefinedFieldSettings(v-else-if="fieldgroup.type == 'predefined'"
                    v-model="layout.fieldgroups[fieldgroup.identifier]"
                    :fieldgroup="fieldgroup")
</template>
