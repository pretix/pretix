<script setup lang="ts">
import { computed, inject } from 'vue'
import type { DayEntry } from '~/types'
import { StoreKey } from '~/sharedStore'
import EventCalendarEvent from './EventCalendarEvent.vue'

const props = defineProps<{
	day: DayEntry | null
	mobile: boolean // TODO inject?
}>()

const store = inject(StoreKey)!

const id = computed(() => props.day ? `${store.htmlId}-${props.day.date}` : '')

const dayhead = computed(() => {
	if (!props.day) return ''
	return props.day.day_formatted
})

const classObject = computed(() => {
	const o: Record<string, boolean> = {}
	if (props.day && props.day.events.length > 0) {
		o['pretix-widget-has-events'] = true
		let best = 'red'
		let allLow = true
		for (const ev of props.day.events) {
			if (ev.availability.color === 'green') {
				best = 'green'
				if (ev.availability.reason !== 'low') {
					allLow = false
				}
			} else if (ev.availability.color === 'orange' && best !== 'green') {
				best = 'orange'
			}
		}
		o[`pretix-widget-day-availability-${best}`] = true
		if (best === 'green' && allLow) {
			o['pretix-widget-day-availability-low'] = true
		}
	}
	return o
})

function selectDay () {
	if (!props.day || !props.day.events.length || !props.mobile) return

	if (props.day.events.length === 1) {
		const ev = props.day.events[0]
		// TODO store mutation bad
		store.parentStack.push(store.targetUrl)
		store.targetUrl = ev.event_url
		store.error = null
		store.subevent = ev.subevent ?? null
		store.loading++
		store.reload()
	} else {
		store.events = props.day.events
		store.view = 'events'
	}
}
</script>
<template lang="pug">
div(:class="classObject", @click.prevent.stop="selectDay")
	.pretix-widget-event-calendar-day(v-if="day", :id="id") {{ dayhead }}
	.pretix-widget-event-calendar-events(v-if="day")
		EventCalendarEvent(
			v-for="e in day.events",
			:key="e.event_url",
			:event="e",
			:describedby="id"
		)
</template>
<style lang="sass">
</style>
