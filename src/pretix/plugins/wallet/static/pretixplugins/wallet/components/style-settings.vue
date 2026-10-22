<script setup lang="ts">
import { inject } from "vue";
import PlaceholderFieldSettings from "./placeholder-field-settings.vue";
import PredefinedFieldSettings from "./predefined-field-settings.vue";
import SettingsField from "./settings-field.vue";
import { StoreKey } from "../walletStore.js";
const gettext = (window as any).gettext;

const store = inject(StoreKey)!;
</script>

<template lang="pug">
    h2.h3 {{  gettext("Settings") }}
    SettingsField(v-for="field of store.style.settings" :field="field" :key="field.identifier")
    h2.h3 {{ gettext("Field Groups") }}
    div(v-for="(fieldgroup, fieldgroupId) in store.style.fieldgroups" :id="'fieldgroup-' + fieldgroup.identifier")
        PlaceholderFieldSettings(
            v-if="fieldgroup.type == 'placeholder'"
            v-model="store.layout.fieldgroups[fieldgroup.identifier]"
            :fieldgroup="fieldgroup"
        )
        PredefinedFieldSettings(v-else-if="fieldgroup.type == 'predefined'"
                    v-model="store.layout.fieldgroups[fieldgroup.identifier]"
                    :fieldgroup="fieldgroup")
</template>
