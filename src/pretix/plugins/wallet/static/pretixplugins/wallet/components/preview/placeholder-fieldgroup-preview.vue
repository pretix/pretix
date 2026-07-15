<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import { i18nstringLocalize } from "../../helpers";

const store = inject(StoreKey)!;

const props = defineProps<{
	config: PreviewFieldgroup;
	style_def: PlaceholderFieldGroupDefinition;
}>();
</script>

<template lang="pug">
    // TODO: support predefined group
    div.fieldgroup-container(:style="{'flex-grow': config.relSize, 'flex-direction': config.direction || 'row'}")
        div.fieldgroup-item(v-for="{ entry, label, content } in store.currentLayoutFieldContent[config.fieldgroup]")
            div.fieldgroup-item-qrcode(v-if="style_def.display == 'code'") {{ label }}

            template(v-else)
                div.fieldgroup-label.nowrap(v-if="style_def.display == 'with_label'") {{ label }}
                div.nowrap.content(v-if="style_def.content_type == 'text'" :class="config.display") {{ content }}
                img.fieldgroup-item-image(v-else-if="style_def.content_type == 'image' && content" :src="i18nstringLocalize(content)")


</template>

<style lang="css" scoped>
.fieldgroup-container {
	min-width: 0;
	display: flex;
	gap: 0.5em;
    min-height: 2lh;
}
.fieldgroup-label {
	font-weight: bold;
	font-size: 0.8em;
}
.fieldgroup-item {
	flex: 0 1 100%;
	min-width: 0;
    width: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.fieldgroup-item-image {
    max-height: 3lh;
}
.fieldgroup-item-qrcode {
    font-weight: bold;
    background-color: lightgray;
    width: 50%;
    aspect-ratio: 1;
    margin: auto;
    /* center content */
    display: flex;
	align-items: center;
	text-align: center;
    padding: 1em;
    overflow-wrap: anywhere;
}

.nowrap {
	text-overflow: ellipsis;
	overflow: hidden;
	text-wrap: nowrap;
}
.bold {
	font-weight: bold;
}
.large {
	font-size: 1.5em;
}
.tight {
    line-height: 1;
}
</style>
