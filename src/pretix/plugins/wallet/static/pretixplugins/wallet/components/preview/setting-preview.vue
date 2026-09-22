<script setup lang="ts">
import { computed, inject, reactive, toRaw, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import FieldgroupItemPreview from "./fieldgroup-item-preview.vue";
import PredefinedFieldgroupPreview from "./predefined-fieldgroup-preview.vue";

const store = inject(StoreKey)!;

const { config } = defineProps<{
	config: SettingPreview;
}>();

const settingDef = computed(() => {
	return Object.fromEntries(
		store.styles[store.layout.style].settings.map(
			(x) => [x.identifier, x],
		),
	)[config.setting];
});
const settingValue = computed(() => {
	const val = store.settings[config.setting];
	if (settingDef.value.type == "image" && val && 'file' in val && val.file) {
		return URL.createObjectURL(val.file);
	} else {
		return val;
	}
});
</script>

<template lang="pug">
    div.fieldgroup-container(:style="{'flex-grow': config.relSize, 'flex-direction': config.direction || 'row'}")
        FieldgroupItemPreview(:content="settingValue" :content_type="settingDef.type" :display_class="config.display" display="plain")
</template>
