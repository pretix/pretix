<script setup lang="ts">
import { ref } from 'vue'
import StyleSettings from './style-settings.vue'

const STYLES = JSON.parse(document.querySelector('#styles')?.textContent ?? '{}')
const VARIABLES = JSON.parse(document.querySelector('#variables')?.textContent ?? '{}')
const FORM_ERRORS = JSON.parse(document.querySelector('#form_errors')?.textContent ?? '{}')
const FORM_DATA = JSON.parse(document.querySelector('#form_data')?.textContent ?? '{}')

const style = ref<string | null>(FORM_DATA.style ?? null)
const name = ref<string>(FORM_DATA.name ?? '')
const layout = ref(JSON.parse(FORM_DATA.layout ?? '{}') ?? {})
</script>

<template lang="pug">
    // TODO: add :key for all `v-for`s
    //- pre
    //-     code {{ STYLES }}
    .row
        .col-md-8
            .form-group(:class='"name" in FORM_ERRORS ? "has-error" : ""')
                label.control-label(for="layout-info-name") Name
                input#layout-info-name.form-control(v-model="name" name="name")

            .form-group(:class='"style" in FORM_ERRORS ? "has-error" : ""')
                label.control-label(for="layout-info-style") Style
                select#layout-info-style.form-control(v-model="style" name="style")
                    option(v-for="styleconfig in STYLES" :key="styleconfig.identifier" :value="styleconfig.identifier") {{ styleconfig.name }}

            StyleSettings(v-model="layout" :style="style" :styles="STYLES" :variables="VARIABLES")
        .col-md-4
            .panel.panel-default
                .panel-heading Preview
                    // TODO: i18n
                .panel-body
                    // TODO: Preview
                    pre
                        code {{ layout }}
        input(type="hidden" name="layout" :value="JSON.stringify(layout)")
    .form-group.submit-group
        button.btn.btn-primary.btn-save(type="submit") Submit
</template>
