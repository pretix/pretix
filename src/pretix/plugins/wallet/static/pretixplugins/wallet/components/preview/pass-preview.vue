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
            RowPreview(v-for="row of layout" :config="row")
</template>

<style lang="css" scoped>
.pass-container {
    width: 100%;
    max-width: 360px;
    vertical-align: top;
    display: inline-block;

    border: solid 1px #949494;
	border-radius: 1em;
    padding: 1em;

    overflow: hidden
}

.pass-content {
    overflow: scroll;
	display: flex;
	flex-direction: column;
    gap: 1em;
}
</style>

<style lang="css">
.pass-container {
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
        white-space: pre-wrap;
    }
    .fieldgroup-item-image {
        max-height: 3lh;
        object-fit: contain;
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
        justify-content: center;
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
}
</style>