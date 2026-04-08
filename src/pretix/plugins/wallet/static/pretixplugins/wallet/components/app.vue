<script setup lang="ts">
import { ref } from 'vue'
import StyleSettings from './style-settings.vue'
import Select from './input/select.vue'
import Input from './input/input.vue'

const gettext = (window as any).gettext

// TODO: Move to store?
const STYLES: Styles = JSON.parse(document.querySelector('#styles')?.textContent ?? '{}')
const VARIABLES: VariableConfig = JSON.parse(document.querySelector('#variables')?.textContent ?? '{}')
const FORM_ERRORS: Record<string, Array<string>> = JSON.parse(document.querySelector('#form_errors')?.textContent ?? '{}')
const LAYOUT: Layout = JSON.parse(document.querySelector('#layout')?.textContent ?? '{}')

const name = ref<string>(LAYOUT.name ?? '')
const style = ref<string | null>(LAYOUT.style ?? null)
const layout = ref<LayoutData>(LAYOUT.layout ?? {fields: {}})
</script>

<template lang="pug">
    // TODO: add :key for all `v-for`s
    // TODO: i18n
    details
        pre
            code {{ FORM_ERRORS }}
    .row
        .col-md-8
            // TODO: show error text
            .form-group(:class='"name" in FORM_ERRORS ? "has-error" : ""')
                Input(label="Name" v-model="name" name="name" :errors="FORM_ERRORS['name']")

            .form-group(:class='"style" in FORM_ERRORS ? "has-error" : ""')
                Select(label="Style" v-model="style" :choices="Object.values(STYLES).map(x => [x.identifier, x.name])" name="style" :errors="FORM_ERRORS['style']")

            StyleSettings(v-if="style" v-model="layout" :style="style" :styles="STYLES" :variables="VARIABLES")
        .col-md-4
            .panel.panel-default
                .panel-heading Preview
                .panel-body
                    // TODO: Preview
                    pre
                        code {{ layout }}
        input(type="hidden" name="layout" :value="JSON.stringify(layout)")
    .form-group.submit-group
        button.btn.btn-primary.btn-save(type="submit") Submit
</template>
