<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import PlaceholderFieldgroupPreview from "./placeholder-fieldgroup-preview.vue";
import PredefinedFieldgroupPreview from "./predefined-fieldgroup-preview.vue";

const store = inject(StoreKey)!;

const props = defineProps<{
	config: PreviewFieldgroup;
}>();

const style_def = computed(() => {
	return Object.fromEntries(
		store.currentPlatformStyles[
			store.currentPlatformLayout.style
		].fieldgroups.map((x) => [x.identifier, x]),
	)[props.config.fieldgroup];
});
</script>

<template lang="pug">
    PlaceholderFieldgroupPreview(v-if="style_def && style_def.type == 'placeholder'" :config="config" :style_def="style_def")
    PredefinedFieldgroupPreview(v-else-if="style_def && style_def.type == 'predefined'" :config="config" :style_def="style_def")
</template>
