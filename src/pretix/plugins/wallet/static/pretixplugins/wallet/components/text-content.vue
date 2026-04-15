<script setup lang="ts">
import { computed, reactive } from 'vue'
import Select from './input/select.vue'
import I18nInput from './input/i18ninput.vue'

const gettext = (window as any).gettext

const props = defineProps<{
	variables: Variables
    locales: Record<string, string>;
}>()
const entry = defineModel<FieldEntry>({ required: true })

const selectChoices = computed(() =>{
    const choices = Object.entries(props.variables).map(([k,v]): [string, string] => [k, v.label])
    choices.push(["other", gettext("Other…")])
    return choices
});

const selection = computed({
    get() {
        if (entry.value.type === 'placeholder') {
            return entry.value.content
        } else if (entry.value.type === 'text') {
            return "other"
        } else {
            throw new Error(`Unknown entry type "${entry.value.type}"`);
        }
    },
    set(newValue) { 
        if (newValue == "other") {
            entry.value.type = "text"
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
        } else if (entry.value.type === 'text') {
            return entry.value.content
        } else {
            throw new Error(`Unknown entry type "${entry.value.type}"`);
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
            :choices="selectChoices"
        )
        I18nInput(v-model="textContent" v-if="selection === 'other'" :locales="locales")
</template>
