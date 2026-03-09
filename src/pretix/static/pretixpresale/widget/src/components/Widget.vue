<script setup lang="ts">
import { computed, inject, ref, onMounted, watch } from 'vue'
import { StoreKey } from '~/sharedStore'
import { STRINGS } from '~/i18n'
import EventForm from './EventForm.vue'
import EventList from './EventList.vue'
import EventCalendar from './EventCalendar.vue'
import EventWeekCalendar from './EventWeekCalendar.vue'
import Overlay from './Overlay.vue'

const emit = defineEmits<{
	mounted: []
}>()

const store = inject(StoreKey)!

const wrapper = ref<HTMLDivElement>()
const formcomp = ref<InstanceType<typeof EventForm>>()
const mobile = ref(false)

const classObject = computed(() => ({
	'pretix-widget': true,
	'pretix-widget-mobile': mobile.value,
	'pretix-widget-use-custom-spinners': true,
}))

watch(mobile, (newValue) => {
	store.mobile = newValue
})

onMounted(() => {
	if (wrapper.value) {
		const resizeObserver = new ResizeObserver((entries) => {
			mobile.value = entries[0].contentRect.width <= 800
		})
		resizeObserver.observe(wrapper.value)
	}

	store.reload() // TODO call earlier?
	emit('mounted') // TODO where does this go?
})

watch(() => store.view, (newValue, oldValue) => {
	if (oldValue && wrapper.value) {
		// always make sure the widget is scrolled to the top
		// as we only check top, we do not need to wait for a redraw
		const rect = wrapper.value.getBoundingClientRect()
		if (rect.top < 0) {
			wrapper.value.scrollIntoView()
		}
	}
})
</script>
<template lang="pug">
.pretix-widget-wrapper(ref="wrapper", tabindex="0", role="article", :aria-label="store.name")
	div(:class="classObject")
		.pretix-widget-loading(v-show="store.loading > 0")
			svg(width="128", height="128", viewBox="0 0 1792 1792", xmlns="http://www.w3.org/2000/svg")
				path.pretix-widget-primary-color(d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z")

		.pretix-widget-error-message(v-if="store.error && store.view !== 'event'") {{ store.error }}
		.pretix-widget-error-action(v-if="store.error && store.connectionError")
			a.pretix-widget-button(:href="store.newTabTarget", target="_blank") {{ STRINGS.open_new_tab }}

		EventForm(v-if="store.view === 'event'", ref="formcomp")
		EventList(v-if="store.view === 'events'")
		EventCalendar(v-if="store.view === 'weeks'", :mobile="mobile")
		EventWeekCalendar(v-if="store.view === 'days'", :mobile="mobile")

		.pretix-widget-clear
		.pretix-widget-attribution(v-if="store.poweredby", v-html="store.poweredby")

	Overlay
</template>
<style lang="sass">
</style>
