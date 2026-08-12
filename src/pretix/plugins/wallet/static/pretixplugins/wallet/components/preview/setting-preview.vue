<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import FieldgroupItemPreview from "./fieldgroup-item-preview.vue";
import PredefinedFieldgroupPreview from "./predefined-fieldgroup-preview.vue";

const store = inject(StoreKey)!;

const { config } = defineProps<{
	config: SettingPreview;
}>();

const settingDef = computed(() => {
	return Object.fromEntries(
		store.currentPlatformStyles[store.currentPlatformLayout.style].settings.map(
			(x) => [x.identifier, x],
		),
	)[config.setting];
});
const settingValue = computed(() => {
	const val = store.currentLayoutSettings[config.setting];
	if (settingDef.value.type == "image" && val instanceof File) {
		return URL.createObjectURL(val);
	} else {
		return val;
	}
});
</script>

<template lang="pug">
    //- pre
    //-     code {{ settingDef }}
    //- pre
    //-     code {{ config }}
    //- pre
    //-     code {{ settingValue }}
    //- PlaceholderFieldgroupPreview(v-if="style_def && style_def.type == 'placeholder'" :config="config" :style_def="style_def")
    //- PredefinedFieldgroupPreview(v-else-if="style_def && style_def.type == 'predefined'" :config="config" :style_def="style_def")
    div.fieldgroup-container(:style="{'flex-grow': config.relSize, 'flex-direction': config.direction || 'row'}")
        FieldgroupItemPreview(:content="settingValue" :content_type="settingDef.type" :display_class="config.display" display="plain")

</template>
