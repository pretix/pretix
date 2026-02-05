<script setup lang="ts">
import { computed } from 'vue'
import type { CheckinList } from '../api'
import { formatSubevent } from '../i18n'

const props = defineProps<{
	list: CheckinList
}>()

defineEmits<{
	selected: [list: CheckinList]
}>()

const subevent = computed(() => formatSubevent(props.list.subevent))
</script>
<template lang="pug">
a.list-group-item(href="#", @click.prevent="$emit('selected', list)")
	.row
		.col-md-6 {{ list.name }}
		.col-md-6.text-muted {{ subevent }}
</template>
