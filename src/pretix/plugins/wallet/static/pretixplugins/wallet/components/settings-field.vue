<script setup lang="ts">
import Input from "./input/input.vue";
import FileInput from "./input/file-input.vue";
import { inject } from "vue";
import { StoreKey } from "../walletStore";

const gettext = (window as any).gettext;

const props = defineProps<{
	field?: Setting;
}>();
const store = inject(StoreKey)!;

// function uploadFile(e: Event) {
//     // TODO: only store ref, upload when saving, proper handling in store
// 	const [file] = (e.target as HTMLInputElement).files;
//     store.setSetting(props.field.identifier, file)
//     // const settings = store.currentPlatformLayout.layout.settings
//     // const identifier = props.field.identifier;
// 	// fetch("/api/v1/upload", {
// 	// 	method: "POST",
// 	// 	body: file,
// 	// 	headers: {
// 	// 		"content-disposition": `attachment; filename="${encodeURI(file.name)}"`,
// 	// 		"content-type": file.type || "application/octet-stream",
// 	// 		"X-CSRFToken": store.csrfToken,
// 	// 	},
// 	// }).then(x => x.json()).then(x=>settings[identifier] = x.id);
// }
</script>

<template lang="pug">
    div.form-group
        Input(v-if='field.type == "text"' :label="field.label" :type="field.type" :required="field.required" @update:modelValue="(v) => store.setSetting(field.identifier, v)" :modelValue="store.currentLayoutSettings[field.identifier]" :help_text="field.help_text")
        FileInput(v-if='field.type == "image"' :label="field.label" :required="field.required" :help_text="field.help_text" @update:modelValue="(v) => store.setSetting(field.identifier, v)" :modelValue="store.currentLayoutSettings[field.identifier]")
</template>
