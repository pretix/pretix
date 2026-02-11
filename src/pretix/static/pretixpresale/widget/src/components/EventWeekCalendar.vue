<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { StoreKey } from '~/sharedStore'
import { STRINGS } from '~/i18n'
import { getISOWeeks } from '~/utils'
import EventWeekCell from './EventWeekCell.vue'
import EventListFilterForm from './EventListFilterForm.vue'

defineProps<{
	mobile: boolean
}>()

const store = inject(StoreKey)!
const weekcalendar = ref<HTMLDivElement>()

const displayEventInfo = computed(() => store.displayEventInfo || (store.displayEventInfo === null && store.parentStack.length > 0))

const weekname = computed(() => {
	if (!store.week) return ''
	const curWeek = store.week[1]
	const curYear = store.week[0]
	return `${curWeek} / ${curYear}`
})

const id = computed(() => `${store.htmlId}-event-week-table`)

const showFilters = computed(() => !store.disableFilters && store.metaFilterFields.length > 0)

function backToList() {
	store.weeks = null
	store.name = null
	store.frontpageText = null
	store.view = 'events'
}

function prevweek() {
	if (!store.week) return
	let curWeek = store.week[1]
	let curYear = store.week[0]
	curWeek--
	if (curWeek < 1) {
		curYear--
		curWeek = getISOWeeks(curYear)
	}
	store.week = [curYear, curWeek]
	store.loading++
	store.reload({ focus: `#${id.value}` })
}

function nextweek() {
	if (!store.week) return
	let curWeek = store.week[1]
	let curYear = store.week[0]
	curWeek++
	if (curWeek > getISOWeeks(curYear)) {
		curWeek = 1
		curYear++
	}
	store.week = [curYear, curWeek]
	store.loading++
	store.reload({ focus: `#${id.value}` })
}
</script>

<template lang="pug">
.pretix-widget-event-calendar.pretix-widget-event-week-calendar(ref="weekcalendar")
	//- Back navigation
	.pretix-widget-back(v-if="store.events !== null")
		a(href="#", @click.prevent.stop="backToList", role="button")
			| &lsaquo; {{ STRINGS.back }}

	//- Event header
	.pretix-widget-event-header(v-if="displayEventInfo")
		strong {{ store.name }}

	//- Filter
	EventListFilterForm(v-if="showFilters")

	//- Calendar navigation
	.pretix-widget-event-description(
		v-if="store.frontpageText && displayEventInfo",
		v-html="store.frontpageText"
	)
	.pretix-widget-event-calendar-head
		a.pretix-widget-event-calendar-previous-month(href="#", @click.prevent.stop="prevweek", role="button")
			| &laquo; {{ STRINGS.previous_week }}
		|
		strong {{ weekname }}
		|
		a.pretix-widget-event-calendar-next-month(href="#", @click.prevent.stop="nextweek", role="button")
			| {{ STRINGS.next_week }} &raquo;

	//- Actual calendar
	.pretix-widget-event-week-table(:id="id", tabindex="0", :aria-label="weekname")
		.pretix-widget-event-week-col(v-for="d in store.days", :key="d?.date || ''")
			EventWeekCell(:day="d", :mobile="mobile")
</template>

<style lang="sass">
</style>
