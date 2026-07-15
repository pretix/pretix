<script setup lang="ts">
import { inject } from "vue";
import { StoreKey } from "../../walletStore.js";
import RowPreview from "./row-preview.vue";

const store = inject(StoreKey)!;

const props = defineProps<{ layout: Array<PreviewLayout> }>();
</script>

<template lang="pug">
    div.pass-container
        div.pass-content
            RowPreview(v-for="row in layout" :config="row")
</template>
<style lang="css" scoped>
.pass-container {
    margin: 1em;

    width: 100%;
    aspect-ratio: 9 / 11;
    max-width: 360px;
    max-height: 440px;
    vertical-align: top;
    display: inline-block;

    outline: solid 1px #949494;
	border-radius: 1em;

    padding: 1em;
}
.pass-content {
    overflow: scroll;
	display: flex;
	flex-direction: column;
    gap: 1em;
}
</style>
