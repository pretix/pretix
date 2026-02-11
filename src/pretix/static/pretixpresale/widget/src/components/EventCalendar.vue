<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { StoreKey } from '~/sharedStore'
import { STRINGS } from '~/i18n'
import { padNumber } from '~/utils'
import EventCalendarRow from './EventCalendarRow.vue'
import EventListFilterForm from './EventListFilterForm.vue'

defineProps<{
	mobile: boolean
}>()

const store = inject(StoreKey)!
const calendar = ref<HTMLDivElement>()

const displayEventInfo = computed(() => store.displayEventInfo || (store.displayEventInfo === null && store.parentStack.length > 0))

const monthname = computed(() => {
	if (!store.date) return ''
	const monthNum = store.date.substr(5, 2)
	const year = store.date.substr(0, 4)
	return `${STRINGS.months[monthNum]} ${year}`
})

const id = computed(() => `${store.htmlId}-event-calendar-table`)

const ariaLabelledby = computed(() => `${store.htmlId}-event-calendar-table-label`)

const showFilters = computed(() => !store.disableFilters && store.metaFilterFields.length > 0)

function backToList () {
	store.weeks = null
	store.view = 'events'
	store.name = null
	store.frontpageText = null
}

function prevmonth () {
	if (!store.date) return
	let curMonth = parseInt(store.date.substr(5, 2))
	let curYear = parseInt(store.date.substr(0, 4))
	curMonth--
	if (curMonth < 1) {
		curMonth = 12
		curYear--
	}
	store.date = `${curYear}-${padNumber(curMonth, 2)}-01`
	store.loading++
	store.reload({ focus: `#${id.value}` })
}

function nextmonth () {
	if (!store.date) return
	let curMonth = parseInt(store.date.substr(5, 2))
	let curYear = parseInt(store.date.substr(0, 4))
	curMonth++
	if (curMonth > 12) {
		curMonth = 1
		curYear++
	}
	store.date = `${curYear}-${padNumber(curMonth, 2)}-01`
	store.loading++
	store.reload({ focus: `#${id.value}` })
}
</script>

<template lang="pug">
.pretix-widget-event-calendar(ref="calendar")
	//- Back navigation
	.pretix-widget-back(v-if="store.events !== null")
		a(href="#", role="button", @click.prevent.stop="backToList")
			| &lsaquo; {{ STRINGS.back }}

	//- Headline
	.pretix-widget-event-header(v-if="displayEventInfo")
		strong {{ store.name }}
	.pretix-widget-event-description(
		v-if="displayEventInfo && store.frontpageText",
		v-html="store.frontpageText"
	)

	//- Filter
	EventListFilterForm(v-if="showFilters")

	//- Calendar navigation
	.pretix-widget-event-calendar-head
		a.pretix-widget-event-calendar-previous-month(href="#", @click.prevent.stop="prevmonth")
			| &laquo; {{ STRINGS.previous_month }}
		|
		strong(:id="ariaLabelledby") {{ monthname }}
		|
		a.pretix-widget-event-calendar-next-month(href="#", @click.prevent.stop="nextmonth")
			| {{ STRINGS.next_month }} &raquo;

	//- Calendar table
	table.pretix-widget-event-calendar-table(
		:id="id",
		tabindex="0",
		:aria-labelledby="ariaLabelledby"
	)
		thead
			tr
				th(:aria-label="STRINGS.days.MONDAY") {{ STRINGS.days.MO }}
				th(:aria-label="STRINGS.days.TUESDAY") {{ STRINGS.days.TU }}
				th(:aria-label="STRINGS.days.WEDNESDAY") {{ STRINGS.days.WE }}
				th(:aria-label="STRINGS.days.THURSDAY") {{ STRINGS.days.TH }}
				th(:aria-label="STRINGS.days.FRIDAY") {{ STRINGS.days.FR }}
				th(:aria-label="STRINGS.days.SATURDAY") {{ STRINGS.days.SA }}
				th(:aria-label="STRINGS.days.SUNDAY") {{ STRINGS.days.SU }}
		tbody
			EventCalendarRow(
				v-for="(week, idx) in store.weeks",
				:key="idx",
				:week="week",
				:mobile="mobile"
			)
</template>

<style lang="sass">
</style>
