<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import FieldgroupItemPreview from "./fieldgroup-item-preview.vue";

const store = inject(StoreKey)!;

const props = defineProps<{
	style_def: PredefinedFieldGroupDefinition;
	config: PredefinedFieldgroupPreview;
}>();

const isActive = computed(
	() =>
		store.currentPlatformLayout.layout.fieldgroups[props.style_def.identifier]?.active,
);
</script>

<template lang="pug">
	div.fieldgroup-container(v-if="isActive" :style="{'flex-grow': config.relSize, 'flex-direction': config.direction || 'row'}")
		FieldgroupItemPreview(v-for="{ label, content } of config.sample" :label="label" :content="content" content_type="text" display="with_label")
</template>