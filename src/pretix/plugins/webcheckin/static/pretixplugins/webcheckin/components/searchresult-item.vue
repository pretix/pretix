<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Position } from '../api'
import { STRINGS, i18nstringLocalize, formatSubevent } from '../i18n'

const props = defineProps<{
	position: Position
}>()

defineEmits<{
	selected: [position: Position]
}>()

const rootEl = ref<HTMLAnchorElement>()

const status = computed(() => {
	if (props.position.checkins.length) return 'redeemed'
	if (props.position.order__status === 'n' && props.position.order__valid_if_pending) return 'pending_valid'
	if (props.position.order__status === 'n' && props.position.order__require_approval) return 'require_approval'
	return props.position.order__status
})

const itemvar = computed(() => {
	if (props.position.variation) {
		return `${i18nstringLocalize(props.position.item.name)} – ${i18nstringLocalize(props.position.variation.value)}`
	}
	return i18nstringLocalize(props.position.item.name)
})

const subevent = computed(() => formatSubevent(props.position.subevent))

defineExpose({ el: rootEl })
</script>
<template lang="pug">
a.list-group-item.searchresult(ref="rootEl", href="#", @click.prevent="$emit('selected', position)")
	.details
		h4 {{ position.order }}-{{ position.positionid }} {{ position.attendee_name }}
		span {{ itemvar }}
			br
		span(v-if="subevent") {{ subevent }}
			br
		.secret {{ position.secret }}
	.status(:class="`status-${status}`")
		span(v-if="position.require_attention")
			span.fa.fa-warning
			br
		| {{ STRINGS[`status.${status}`] }}
</template>
