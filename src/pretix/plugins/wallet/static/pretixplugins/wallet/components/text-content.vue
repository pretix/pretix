<script setup lang="ts">
import { computed, inject, reactive } from 'vue'
import Select from './input/select.vue'
import I18nInput from './input/i18ninput.vue'
import { StoreKey } from "../walletStore";

const store = inject(StoreKey)!
const gettext = (window as any).gettext

const props = defineProps<{
	placeholderChoices: [string|null, string][];
}>();

const entry = defineModel<FieldEntry>({ required: true })

const selection = computed({
    get() {
        if (entry.value.type === 'placeholder') {
            return entry.value.content
        } else if (entry.value.type === 'custom') {
            return "other"
        }
    },
    set(newValue) {
        if (newValue == "other") {
            entry.value.type = "custom"
            entry.value.content = {};
        } else {
            entry.value.type = "placeholder"
            entry.value.content = newValue
        }
    }
})

const textContent = computed({
    get() {
        if (entry.value.type === 'placeholder') {
            return ""
        } else if (entry.value.type === 'custom') {
            return entry.value.content
        }
    },
    set(newValue) {
        entry.value.content = newValue
    }
})

</script>

<template lang="pug">
    .i18n-form-group
        Select(
            v-model="selection"
            :choices="placeholderChoices"
        )
        I18nInput(v-model="textContent" v-if="selection === 'other'" :locales="store.locales")
</template>
