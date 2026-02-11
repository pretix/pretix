<script setup lang="ts">
import type { DayEntry } from '~/types'
import EventCalendarCell from './EventCalendarCell.vue'

defineProps<{
	week: (DayEntry | null)[]
	mobile: boolean
}>()
</script>

<template lang="pug">
tr
	EventCalendarCell(v-for="(d, idx) in week", :key="idx", :day="d", :mobile="mobile")
</template>

<style lang="sass">
</style>
