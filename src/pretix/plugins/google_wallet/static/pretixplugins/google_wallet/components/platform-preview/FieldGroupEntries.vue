<script setup lang="ts">
const props = defineProps<{
	fieldgroup: string;
	fieldgroupContents: Record<string, any>;
}>()

function focusGroup () {
	// TODO: highlight group? or change ui concept completely
	const elem = document.getElementById('fieldgroup-' + props.fieldgroup)
	if (elem) {
		elem.scrollIntoView()
	}
}

</script>

<template lang="pug">
	div(@click="focusGroup")
		div(v-for="entry in fieldgroupContents[fieldgroup]")
			div.pass-label {{ entry.label }}
			div.pass-content {{ entry.content }}
</template>
