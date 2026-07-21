<script setup lang="ts">
import FieldgroupPreview from './fieldgroup-preview.vue';
import FixedPreview from './fixed-preview.vue';

const props = defineProps<{
    config: Record<string, string>;
}>();

</script>

<template lang="pug">
    div.preview-row(v-if="'children' in config" :style="{flexDirection: config.direction || 'row'}")
        RowPreview(v-for="child of config.children" :config="child")
    FieldgroupPreview(v-else-if="'fieldgroup' in config" :config="config")
    FixedPreview(v-else-if="'value' in config" :config="config")

</template>
<style lang="css" scoped>
.preview-row {
width: 100%; display: flex; gap: 1em; display: flex
}
</style>