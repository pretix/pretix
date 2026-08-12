<script setup lang="ts">
import Input from "./input/input.vue";
import FileInput from "./input/file-input.vue";
import { inject } from "vue";
import { StoreKey } from "../walletStore";

const props = defineProps<{
	field?: Setting;
}>();
const store = inject(StoreKey)!;
</script>

<template lang="pug">
    div.form-group
        Input(v-if='field.type == "text"' :label="field.label" :type="field.type" :required="field.required" @update:modelValue="(v) => store.setSetting(field.identifier, v)" :modelValue="store.settings[field.identifier]" :help_text="field.help_text")
        FileInput(v-if='field.type == "image"' :label="field.label" :required="field.required" :help_text="field.help_text" @change="(v) => store.setSetting(field.identifier, v)" :filename="store.settings[field.identifier]?.name" :current_url="store.settings[field.identifier]?.name")
</template>
