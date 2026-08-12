<script setup lang="ts">
import FieldgroupItemPreview from './fieldgroup-item-preview.vue';
import FieldgroupPreview from './fieldgroup-preview.vue';
import SettingPreview from './setting-preview.vue';
const props = defineProps<{
    config: PreviewRow;
}>();

</script>

<template lang="pug">
    div.preview-row(v-if="'children' in config" :style="{ flexDirection: config.direction || 'row' }" :class="config.display")
        RowPreview(v-for="child of config.children" :config="child" )
    FieldgroupPreview(v-else-if="'fieldgroup' in config" :config="config")
    FieldgroupItemPreview(v-else-if="'value' in config" :label="config.label" :content="config.value" content_type="text" :display="!!config.label ? 'with_label' : 'plain'" :display_class="config.display")
    SettingPreview(v-else-if="'setting' in config" :config="config")

</template>
<style lang="css" scoped>
.preview-row {
    width: 100%;
    display: flex;
    gap: 1em;
    display: flex
}
.tight {
    gap: 0;
}
</style>