<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from 'vue'

const props = defineProps<{
	fieldgroup: string;
	fieldgroup_contents: Record<string, any>;
}>()

function focusGroup () {
	// TODO: highlight group? or change ui concept completely
	const elem = document.getElementById('fieldgroup-' + props.fieldgroup)
	elem && elem.scrollIntoView()
}

</script>

<template lang="pug">
	div(@click="focusGroup")
		div(v-for="entry in fieldgroup_contents[fieldgroup]")
			div.pass-label {{ entry.label }}
			div.pass-content {{ entry.content }}
</template>
