<script setup lang="ts">
import { computed, reactive, watchEffect } from "vue";
import Select from "./input/select.vue";
import Input from "./input/input.vue";
import I18nInput from "./input/i18ninput.vue";
import TextContent from "./text-content.vue";

const gettext = (window as any).gettext;

const props = defineProps<{
	fieldgroup: FieldGroupDefinition;
	overflows: FieldGroupDefinition[];
	variables: Variables;
    locales: Record<string, string>;
}>();
const fieldConfig = defineModel<PlaceholderFieldGroupConfig>({ required: true });

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
	fieldConfig.value.entries.push({ type: "placeholder", label: "" });
}

watchEffect(() => {
    if (!fieldConfig.value) {
        fieldConfig.value = {overflow: null, entries: JSON.parse(JSON.stringify(props.fieldgroup.default_entries))};
    }
    if (fieldConfig.value && !fieldConfig.value.entries) {
        fieldConfig.value.entries = JSON.parse(JSON.stringify(props.fieldgroup.default_entries))
    }
});
</script>

<template lang="pug">
    .panel.panel-default
        .panel-heading
            h3.panel-title {{ fieldgroup.name }}
        .panel-body(v-if="fieldConfig")
            .form-group()
                span.text-muted(v-if="fieldgroup.description") {{ fieldgroup.description }}
                h4 {{ gettext("Content") }}
                .row.form-group(v-for="n in fieldConfig.entries.length")
                    .col-md-5(v-if="fieldgroup.labels")
                        I18nInput(:label="gettext('Label')" v-model="fieldConfig.entries[n-1].label" :locales="locales")
                    div(:class="'col-md-' + (fieldgroup.labels ? '6' : '11')")
                        TextContent(v-if='fieldgroup.content_type == "text"'
                                    v-model="fieldConfig.entries[n-1]"
                                    :variables="props.variables")
                        Select(:label="gettext('Content')"
                                v-else-if='fieldgroup.content_type == "image"'
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
