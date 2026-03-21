<script setup lang="ts">
import { computed, inject, nextTick } from 'vue'
import { StoreKey } from '~/sharedStore'
import { STRINGS } from '~/i18n'
import EventListEntry from './EventListEntry.vue'
import EventListFilterForm from './EventListFilterForm.vue'

const store = inject(StoreKey)!

const displayEventInfo = computed(() => store.displayEventInfo || (store.displayEventInfo === null && store.parentStack.length > 0))

async function backToCalendar (event: MouseEvent) {
	// make sure to always focus content element
	await nextTick()
	const rootEl = (event.target as HTMLElement).closest('.pretix-widget-wrapper') as HTMLElement | null
	rootEl?.focus()

	store.offset = 0
	store.appendEvents = false

	if (store.weeks) {
		store.events = null
		store.view = 'weeks'
		store.name = null
		store.frontpageText = null
	} else {
		store.loading++
		store.targetUrl = store.parentStack.pop() || store.targetUrl
		store.error = null
		store.reload()
	}
}

function loadMore () {
	store.appendEvents = true
	store.offset += 50
	store.loading++
	store.reload()
}

console.log(store)
</script>
<template lang="pug">
.pretix-widget-event-list
	.pretix-widget-back(v-if="store.weeks || store.parentStack.length > 0")
		a(href="#", rel="prev", @click.prevent.stop="backToCalendar")
			| &lsaquo; {{ STRINGS.back }}

	.pretix-widget-event-header(v-if="displayEventInfo")
		strong {{ store.name }}

	.pretix-widget-event-description(
		v-if="displayEventInfo && store.frontpageText",
		v-html="store.frontpageText"
	)

	EventListFilterForm(v-if="!store.disableFilters && store.metaFilterFields.length > 0")

	EventListEntry(
		v-for="event in store.events",
		:key="event.event_url",
		:event="event"
	)

	p.pretix-widget-event-list-load-more(v-if="store.hasMoreEvents")
		button(@click.prevent.stop="loadMore") {{ STRINGS.load_more }}
</template>
<style lang="sass">
</style>
