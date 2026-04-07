<script setup lang="ts">
import { computed } from 'vue'
import OptionalSelect from './optional-select.vue'

const props = defineProps<{
	field: any // TODO
	overflows: [string, string][],
	variables: any // TODO
}>()
const fieldConfig = defineModel<any>({ required: true })

const overflowOptions = computed(() => {
	if (props.overflows.length) {
		return [...props.overflows.map(x => [x.identifier, x.name]), [null, "Do not overflow"]]
	} else {
		return []
	}
})

function addVariable() {
	fieldConfig.value.entries.push({"label": null, "value": null})
}
</script>

<template lang="pug">
    //- pre
    //-     code {{ props }}
    .panel.panel-default
        .panel-heading
            h3.panel-title {{ field.name }}
        .panel-body
            .form-group(v-if="props.variables[field.entry_type]")
                span.text-muted These fields appear somewhere and are visible too.
                // TODO: for="..." / labeledby?
                h4 Fields
                .row.form-group(v-for="n in fieldConfig.entries.length")
                    .col-md-5
                        // TODO: i18n
                        label.control-label Label
                        input.form-control(v-model="fieldConfig.entries[n-1].label")
                    .col-md-6
                        label.control-label Value
                        select.form-control(v-model="fieldConfig.entries[n-1].value")
                            option(v-for="(config, id) in props.variables[field.entry_type]" :key="id" :value="id") {{ config.label }}
                    .col-md-1
                        label.control-label &nbsp;
                            span.sr-only "Delete"
                        button.btn.btn-danger(type="button" @click="fieldConfig.entries.splice(n-1, 1)")
                            i.fa.fa-trash
                            span.sr-only "Delete"
                button.btn.btn-default(type="button" @click="addVariable")
                    i.fa.fa-plus
                    span.sr-only Add field
            OptionalSelect(label="Overflow to ..." :choices="overflowOptions" v-model="fieldConfig.overflow")
</template>
