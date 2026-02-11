<script setup lang="ts">
import { computed, inject } from 'vue'
import type { EventEntry } from '~/types'
import { StoreKey } from '~/sharedStore'

const props = defineProps<{
	event: EventEntry
	describedby?: string
}>()

const store = inject(StoreKey)!

const classObject = computed(() => {
	const o: Record<string, boolean> = {
		'pretix-widget-event-calendar-event': true,
	}
	o[`pretix-widget-event-availability-${props.event.availability.color}`] = true
	if (props.event.availability.reason) {
		o[`pretix-widget-event-availability-${props.event.availability.reason}`] = true
	}
	return o
})

function select() {
	store.parentStack.push(store.targetUrl)
	store.targetUrl = props.event.event_url
	store.error = null
	store.subevent = props.event.subevent ?? null
	store.loading++
	store.reload()
}
</script>

<template lang="pug">
a.pretix-widget-event-calendar-event(
	href="#",
	:class="classObject",
	@click.prevent.stop="select",
	:aria-describedby="describedby"
)
	strong.pretix-widget-event-calendar-event-name {{ event.name }}
	.pretix-widget-event-calendar-event-date(v-if="!event.continued && event.time") {{ event.time }}
	.pretix-widget-event-calendar-event-availability(v-if="!event.continued && event.availability.text") {{ event.availability.text }}
</template>

<style lang="sass">
</style>
