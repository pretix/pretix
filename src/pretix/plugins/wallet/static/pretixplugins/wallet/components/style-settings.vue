<script setup lang="ts">
import { computed, inject, watchEffect } from "vue";
import PlaceholderFieldSettings from "./placeholder-field-settings.vue";
import PredefinedFieldSettings from "./predefined-field-settings.vue";
import SettingsField from "./settings-field.vue";
const gettext = (window as any).gettext;

const props = defineProps<{
	style?: Style;
}>();

const layout = defineModel<LayoutData>();
</script>

<template lang="pug">
    h2.h3 {{  gettext("Settings") }}
    SettingsField(v-for="field of style.settings" :field="field" :key="field.identifier")
    h2.h3 {{ gettext("Field Groups") }}
    div(v-if="props.style && layout.fieldgroups"
             v-for="(fieldgroup, fieldgroupId) in props.style.fieldgroups" :id="'fieldgroup-' + fieldgroup.identifier")
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
