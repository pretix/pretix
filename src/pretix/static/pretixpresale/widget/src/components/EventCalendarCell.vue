<script setup lang="ts">
import { computed, inject, ref, onMounted, watch } from 'vue'
import type { DayEntry } from '~/types'
import { StoreKey } from '~/sharedStore'
import EventCalendarEvent from './EventCalendarEvent.vue'

const props = defineProps<{
	day: DayEntry | null
	mobile: boolean
}>()

const store = inject(StoreKey)!
const cellEl = ref<HTMLTableCellElement>()

const daynum = computed(() => {
	if (!props.day) return ''
	return props.day.date.substr(8)
})

const dateStr = computed(() => props.day ? new Date(props.day.date).toLocaleDateString() : '')

const role = computed(() => !props.day || !props.day.events.length || !props.mobile ? 'cell' : 'button')

const tabindex = computed(() => role.value === 'button' ? '0' : '-1')

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

function selectDay(e: Event) {
	if (!props.day || !props.day.events.length || !props.mobile) return
	e.preventDefault()
	e.stopPropagation()

	if (props.day.events.length === 1) {
		const ev = props.day.events[0]
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

function onKeyDown(e: KeyboardEvent) {
	const keyDown = e.key ?? e.keyCode
	if (keyDown === 'Enter' || keyDown === 13 || ['Spacebar', ' '].includes(keyDown as string) || keyDown === 32) {
		e.preventDefault()
		selectDay(e)
	}
}

function attachListeners() {
	if (role.value === 'button' && cellEl.value) {
		cellEl.value.addEventListener('click', selectDay)
		cellEl.value.addEventListener('keydown', onKeyDown)
	}
}

function detachListeners() {
	if (cellEl.value) {
		cellEl.value.removeEventListener('click', selectDay)
		cellEl.value.removeEventListener('keydown', onKeyDown)
	}
}

onMounted(() => {
	attachListeners()
})

watch(role, (newValue, oldValue) => {
	if (newValue === 'button' && oldValue !== 'button') {
		attachListeners()
	} else if (newValue !== 'button' && oldValue === 'button') {
		detachListeners()
	}
})
</script>

<template lang="pug">
td(
	ref="cellEl",
	:class="classObject",
	:role="role",
	:tabindex="tabindex",
	:aria-label="dateStr"
)
	.pretix-widget-event-calendar-day(v-if="day", :aria-label="dateStr") {{ daynum }}
	.pretix-widget-event-calendar-events(v-if="day")
		EventCalendarEvent(v-for="e in day.events", :key="e.event_url", :event="e")
</template>

<style lang="sass">
</style>
