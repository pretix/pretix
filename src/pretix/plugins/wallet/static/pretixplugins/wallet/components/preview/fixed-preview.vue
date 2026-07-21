<script setup lang="ts">
const props = defineProps<{
    config: {value: string; label?: string; display?: string};
}>();

</script>

<template lang="pug">
    div.fieldgroup-item
        div.fieldgroup-label.nowrap(v-if="!!config.label") {{ config.label }}
        div.nowrap.content(:class="config.display") {{ config.value }}
</template>


<style lang="css" scoped>
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