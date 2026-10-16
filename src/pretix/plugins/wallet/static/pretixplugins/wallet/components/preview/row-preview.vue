<script setup lang="ts">
import FieldgroupItemPreview from './fieldgroup-item-preview.vue';
import FieldgroupPreview from './fieldgroup-preview.vue';
import SettingPreview from './setting-preview.vue';
const props = defineProps<{
    config: PreviewRow;
}>();

</script>

<template lang="pug">
    div.preview-row(v-if="'children' in config" :style="config.style" :class="config.display_class")
        RowPreview(v-for="child of config.children" :config="child" )
    FieldgroupItemPreview(v-else-if="'content' in config" :label="config.label" :content="config.content" :content_type="config.content_type || 'text'" :display="config.display || (!!config.label ? 'with_label' : 'plain')" :display_class="config.display_class")

</template>
<style lang="css" scoped>
.preview-row {
    width: 100%;
    display: flex;
    gap: 1em;
}
</style>