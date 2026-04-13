<script setup lang="ts">
import { computed, reactive } from "vue";
import Select from "./input/select.vue";
import Input from "./input/input.vue";
import TextContent from "./text-content.vue";

const gettext = (window as any).gettext;

const props = defineProps<{
	field: FieldGroupDefinition;
	overflows: FieldGroupDefinition[];
	variables: Variables;
}>();
const fieldConfig = defineModel<FieldConfig>({ required: true });

const overflowOptions = computed((): Array<[string | null, string]> => {
	if (props.overflows.length) {
		return [
			...props.overflows.map((x): [string, string] => [x.identifier, x.name]),
			[null, "Do not overflow"],
		];
	} else {
		return [];
	}
});

function addVariable() {
	fieldConfig.value.entries.push({ type: "placeholder" });
}
</script>

<template lang="pug">
    .panel.panel-default
        .panel-heading
            h3.panel-title {{ field.name }}
        .panel-body
            .form-group
                span.text-muted These fields appear somewhere and are visible too.
                h4 {{ gettext("Content") }}
                .row.form-group(v-for="n in fieldConfig.entries.length")
                    .col-md-5
                        Input(:label="gettext('Label')" v-model="fieldConfig.entries[n-1].label")
                    .col-md-6(v-if='field.entry_type == "text"')
                        TextContent(v-model="fieldConfig.entries[n-1]"
                                    :variables="props.variables")
                    .col-md-6(v-else-if='field.entry_type == "image"')
                        Select(:label="gettext('Content')"
                                       v-model="fieldConfig.entries[n-1].content"
                                       :choices="Object.entries(props.variables).map(([k,v]) => [k, v.label])"
                                    )
                    .col-md-1
                        label.control-label &nbsp;
                            span.sr-only {{ gettext('Delete')}}
                        button.btn.btn-danger(type="button" @click="fieldConfig.entries.splice(n-1, 1)")
                            i.fa.fa-trash
                            span.sr-only {{ gettext('Delete')}}
                button.btn.btn-default(type="button" @click="addVariable")
                    i.fa.fa-plus
                    span.sr-only {{ gettext("Add field") }}
            Select(:label="gettext('Overflow to …')" :choices="overflowOptions" v-model="fieldConfig.overflow")
</template>
