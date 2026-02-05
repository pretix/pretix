<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api'
import type { CheckinList } from '../api'
import { STRINGS } from '../i18n'
import CheckinlistItem from './checkinlist-item.vue'

const emit = defineEmits<{
	selected: [list: CheckinList]
}>()

const loading = ref(false)
const error = ref<unknown>(null)
const lists = ref<CheckinList[] | null>(null)
const nextUrl = ref<string | null>(null)

async function load () {
	loading.value = true
	error.value = null

	try {
		if (location.hash) {
			const listId = location.hash.substring(1)
			try {
				const data = await api.fetchCheckinList(listId)
				loading.value = false
				if (data.id) {
					emit('selected', data)
					load()
				}
			} catch {
				location.hash = ''
				load()
			}
			return
		}

		const data = await api.fetchCheckinLists()
		loading.value = false

		if (data.results) {
			lists.value = data.results
			nextUrl.value = data.next
		} else if (data.results === 0) {
			error.value = STRINGS['checkinlist.none']
		} else {
			error.value = data
		}
	} catch (e) {
		loading.value = false
		error.value = e
	}
}

async function loadNext () {
	if (!nextUrl.value) return

	loading.value = true
	error.value = null

	try {
		const data = await api.fetchNextPage<CheckinList>(nextUrl.value)
		loading.value = false

		if (data.results) {
			lists.value.push(...data.results)
			nextUrl.value = data.next
		} else if (data.results === 0) {
			error.value = STRINGS['checkinlist.none']
		} else {
			error.value = data
		}
	} catch (e) {
		loading.value = false
		error.value = e
	}
}

onMounted(() => {
	load()
})
</script>
<template lang="pug">
.panel.panel-primary.checkinlist-select
	.panel-heading
		h3.panel-title {{ STRINGS['checkinlist.select'] }}
	ul.list-group
		CheckinlistItem(
			v-for="l in lists",
			:key="l.id",
			:list="l",
			@selected="emit('selected', $event)"
		)
		li.list-group-item.text-center(v-if="loading")
			span.fa.fa-4x.fa-cog.fa-spin.loading-icon
		li.list-group-item.text-center(v-else-if="error") {{ error }}
		a.list-group-item.text-center(v-else-if="nextUrl", href="#", @click.prevent="loadNext")
			| {{ STRINGS['pagination.next'] }}
</template>
