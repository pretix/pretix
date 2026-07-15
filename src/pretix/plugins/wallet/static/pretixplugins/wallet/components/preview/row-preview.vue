<script setup lang="ts">
import FieldgroupPreview from './fieldgroup-preview.vue';

const props = defineProps<{
    config: Record<string, string>;
}>();

</script>

<template lang="pug">
    div(v-if="'children' in config" style="width: 100%; display: flex; gap: 1em")
        RowPreview(v-for="child in config.children" :config="child")
    FieldgroupPreview(v-else :config="config")
</template>