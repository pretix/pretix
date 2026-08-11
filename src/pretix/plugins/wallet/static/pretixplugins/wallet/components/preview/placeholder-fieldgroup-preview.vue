<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import FieldgroupItemPreview from "./fieldgroup-item-preview.vue";

const store = inject(StoreKey)!;

const props = defineProps<{
	config: PreviewFieldgroup;
	style_def: PlaceholderFieldGroupDefinition;
}>();
</script>

<template lang="pug">
    div.fieldgroup-container(:style="{'flex-grow': config.relSize, 'flex-direction': config.direction || 'row'}")
        FieldgroupItemPreview(v-for="{ label, content } of store.currentLayoutFieldContent[config.fieldgroup]" :label="label" :content="content" :content_type="style_def.content_type" :display_class="config.display" :display="style_def.display")
</template>
