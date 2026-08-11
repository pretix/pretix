<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import { i18nstringLocalize } from "../../helpers";

const store = inject(StoreKey)!;

const props = defineProps<{
	label: I18nString;
	content: I18nString;
    content_type: FieldContentType;
    display: FieldGroupDisplay;
    display_class?: string | string[];
}>();
</script>

<template lang="pug">
    div.fieldgroup-item
        div.fieldgroup-item-qrcode(v-if="display == 'code'") {{ label }}

        template(v-else)
            div.fieldgroup-label.nowrap(v-if="display == 'with_label'") {{ i18nstringLocalize(label) }}
            div.nowrap.content(v-if="content_type == 'text'" :class="display_class") {{ i18nstringLocalize(content) }}
            img.fieldgroup-item-image(v-else-if="content_type == 'image' && content" :src="i18nstringLocalize(content)")
</template>