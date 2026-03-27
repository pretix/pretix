<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import type { CheckinList, Position, RedeemResponse, CheckinStatus, AnswerQuestion } from '../api'
import { STRINGS, i18nstringLocalize, formatSubevent, formatAnswer } from '../i18n'

import CheckinlistSelect from './checkinlist-select.vue'
import SearchresultItem from './searchresult-item.vue'
import Datefield from './datefield.vue'
import Timefield from './timefield.vue'
import Datetimefield from './datetimefield.vue'

const props = defineProps<{
	eventName?: string
}>()

const COUNTRIES = JSON.parse(document.querySelector('#countries')?.textContent ?? '[]')

let clearTimeoutId: ReturnType<typeof setTimeout> | null = null
const answers = ref<Record<string, string>>({})

// Checkin list selection
const checkinlist = ref<CheckinList | null>(null)
const subevent = computed(() => formatSubevent(checkinlist.value?.subevent))

function selectList (list: CheckinList) {
	checkinlist.value = list
	location.hash = '#' + list.id
	refocus()
	fetchStatus()
}

function switchList () {
	location.hash = ''
	checkinlist.value = null
}

// Entry/Exit type
const type = ref<'entry' | 'exit'>('entry')

function switchType () {
	type.value = type.value === 'exit' ? 'entry' : 'exit'
	refocus()
}

// Input/query
const inputEl = ref<HTMLInputElement>()
const query = ref('')

function refocus () {
	nextTick(() => {
		inputEl.value?.focus()
	})
}

function inputKeyup (e: KeyboardEvent) {
	if (e.key === 'Enter') {
		startSearch(true)
	} else if (query.value === '') {
		clear()
	}
}

function globalKeydown (e: KeyboardEvent | Event) {
	if (!(e instanceof KeyboardEvent)) {
		refocus()
		return
	}

	if (document.activeElement?.classList.contains('searchresult')) {
		if (e.key === 'ArrowDown') {
			(document.activeElement.nextElementSibling as HTMLElement)?.focus()
			e.preventDefault()
			return
		}
		if (e.key === 'ArrowUp') {
			(document.activeElement.previousElementSibling as HTMLElement)?.focus()
			e.preventDefault()
			return
		}
	}

	const nodeName = document.activeElement?.nodeName?.toLowerCase()
	if (nodeName !== 'input' && nodeName !== 'textarea') {
		if (e.key?.match(/^[a-z0-9A-Z+/=<>#]$/)) {
			query.value = ''
			refocus()
		}
	}
}

// Status
const status = ref<CheckinStatus | null>(null)
const statusLoading = ref(0)
let statusInterval: ReturnType<typeof setInterval> | null = null

async function fetchStatus () {
	if (!checkinlist.value) return

	statusLoading.value++
	try {
		status.value = await api.fetchStatus(checkinlist.value.id)
	} finally {
		statusLoading.value--
	}
}

// Check/redeem
const checkLoading = ref(false)
const checkError = ref<string | null>(null)
const checkResult = ref<RedeemResponse | null>(null)

const checkResultAddons = computed(() => {
	if (!checkResult.value?.position?.addons) return ''
	return checkResult.value.position.addons.map((addon) => {
		if (addon.variation) {
			return `+ ${addon.item.internal_name || i18nstringLocalize(addon.item.name)} – ${i18nstringLocalize(addon.variation.value)}`
		}
		return '+ ' + (addon.item.internal_name || i18nstringLocalize(addon.item.name))
	}).join('\n')
})

const checkResultSubevent = computed(() => formatSubevent(checkResult.value?.position?.subevent))

const checkResultItemvar = computed(() => {
	if (!checkResult.value?.position) return ''
	if (checkResult.value.position.variation) {
		return `${i18nstringLocalize(checkResult.value.position.item.name)} – ${i18nstringLocalize(checkResult.value.position.variation.value)}`
	}
	return i18nstringLocalize(checkResult.value.position.item.name)
})

const checkResultText = computed(() => {
	if (!checkResult.value) return ''
	if (checkResult.value.status === 'ok') {
		return type.value === 'exit' ? STRINGS['result.exit'] : STRINGS['result.ok']
	} else if (checkResult.value.status === 'incomplete') {
		return STRINGS['result.questions']
	} else if (checkResult.value.reason && STRINGS['result.' + checkResult.value.reason]) {
		return STRINGS['result.' + checkResult.value.reason]
	}
	return checkResult.value.reason ?? ''
})

const checkResultColor = computed(() => {
	if (!checkResult.value) return ''
	if (checkResult.value.status === 'ok') return 'green'
	if (checkResult.value.status === 'incomplete') return 'purple'
	if (checkResult.value.reason === 'already_redeemed') return 'orange'
	return 'red'
})

// Modals
const showUnpaidModal = ref(false)
const showQuestionsModal = ref(false)
const questionsModalEl = ref<HTMLFormElement>()

function answerSetM (qid: string, opid: string, checked: boolean) {
	let arr = answers.value[qid] ? answers.value[qid].split(',') : []
	if (checked && !arr.includes(opid)) {
		arr.push(opid)
	} else if (!checked) {
		arr = arr.filter(o => opid !== o)
	}
	answers.value[qid] = arr.join(',')
}

// Search
const searchLoading = ref(false)
const searchResults = ref<Position[] | null>(null)
const searchNextUrl = ref<string | null>(null)
const searchError = ref<unknown>(null)
const resultEls = ref<InstanceType<typeof SearchresultItem>[]>([])

function selectResult (position: Position) {
	check(position.secret, false, false, false, false)
}

async function startSearch (fallbackToScan: boolean) {
	if (query.value.length >= 32 && fallbackToScan) {
		check(query.value, false, false, true, true)
		return
	}

	checkResult.value = null
	searchLoading.value = true
	searchError.value = null
	searchResults.value = []
	answers.value = {}

	if (clearTimeoutId) {
		clearTimeout(clearTimeoutId)
		clearTimeoutId = null
	}

	try {
		const data = await api.searchPositions(checkinlist.value!.id, query.value)
		searchLoading.value = false

		if (data.results) {
			searchResults.value = data.results
			searchNextUrl.value = data.next

			if (data.results.length) {
				if (data.results[0].secret === query.value) {
					nextTick(() => {
						inputEl.value?.blur()
						resultEls.value[0]?.el?.click()
					})
				} else {
					nextTick(() => {
						resultEls.value[0]?.el?.focus()
					})
				}
			} else {
				nextTick(() => {
					inputEl.value?.blur()
				})
			}
		} else {
			searchError.value = data
		}

		clearTimeoutId = setTimeout(clear, 30 * 1000)
	} catch (e) {
		searchLoading.value = false
		searchResults.value = []
		searchError.value = e
		clearTimeoutId = setTimeout(clear, 30 * 1000)
	}
}

async function searchNext () {
	if (!searchNextUrl.value) return

	searchLoading.value = true
	searchError.value = null

	if (clearTimeoutId) {
		clearTimeout(clearTimeoutId)
		clearTimeoutId = null
	}

	try {
		const data = await api.fetchNextPage<Position>(searchNextUrl.value)
		searchLoading.value = false

		if (data.results) {
			searchResults.value = [...(searchResults.value ?? []), ...data.results]
			searchNextUrl.value = data.next
		} else {
			searchError.value = data
		}

		clearTimeoutId = setTimeout(clear, 30 * 1000)
	} catch (e) {
		searchLoading.value = false
		searchError.value = e
		clearTimeoutId = setTimeout(clear, 30 * 1000)
	}
}

async function check (
	id: string,
	ignoreUnpaid: boolean,
	keepAnswers: boolean,
	fallbackToSearch: boolean,
	untrusted: boolean
) {
	if (!keepAnswers) {
		answers.value = {}
	} else if (showQuestionsModal.value) {
		if (!questionsModalEl.value?.reportValidity()) return
	}

	showUnpaidModal.value = false
	showQuestionsModal.value = false
	checkLoading.value = true
	checkError.value = null
	checkResult.value = {} as RedeemResponse

	if (clearTimeoutId) {
		clearTimeout(clearTimeoutId)
		clearTimeoutId = null
	}

	nextTick(() => {
		inputEl.value?.blur()
	})

	try {
		const data = await api.redeemPosition(
			checkinlist.value!.id,
			id,
			{
				questions_supported: true,
				canceled_supported: true,
				ignore_unpaid: ignoreUnpaid,
				type: type.value,
				answers: answers.value,
			},
			untrusted
		)

		checkLoading.value = false
		checkResult.value = data

		if (checkinlist.value?.include_pending && data.status === 'error' && data.reason === 'unpaid') {
			showUnpaidModal.value = true
			nextTick(() => {
				document.querySelector<HTMLButtonElement>('.modal-unpaid .btn-primary')?.focus()
			})
		} else if (data.status === 'incomplete' && data.questions) {
			showQuestionsModal.value = true
			for (const q of data.questions) {
				if (!answers.value[q.id.toString()]) {
					answers.value[q.id.toString()] = ''
				}
				;(q as AnswerQuestion).question = i18nstringLocalize(q.question)
				for (const o of q.options) {
					;(o as { answer: string }).answer = i18nstringLocalize(o.answer)
				}
			}
			nextTick(() => {
				document.querySelector<HTMLElement>('.modal-questions input, .modal-questions select, .modal-questions textarea')?.focus()
			})
		} else if (data.status === 'error' && data.reason === 'invalid' && fallbackToSearch) {
			startSearch(false)
		} else {
			clearTimeoutId = setTimeout(clear, 30 * 1000)
			fetchStatus()
		}
	} catch (e) {
		checkLoading.value = false
		checkResult.value = {} as RedeemResponse
		checkError.value = String(e)
		clearTimeoutId = setTimeout(clear, 30 * 1000)
	}
}

function clear () {
	query.value = ''
	searchLoading.value = false
	searchResults.value = null
	searchNextUrl.value = null
	searchError.value = null
	checkLoading.value = false
	checkError.value = null
	checkResult.value = null
	showUnpaidModal.value = false
	showQuestionsModal.value = false
	answers.value = {}
}

onMounted(() => {
	window.addEventListener('focus', globalKeydown)
	document.addEventListener('visibilitychange', globalKeydown)
	document.addEventListener('keydown', globalKeydown)
	statusInterval = setInterval(fetchStatus, 120 * 1000)
})

onUnmounted(() => {
	window.removeEventListener('focus', globalKeydown)
	document.removeEventListener('visibilitychange', globalKeydown)
	document.removeEventListener('keydown', globalKeydown)
	if (statusInterval) clearInterval(statusInterval)
	if (clearTimeoutId) clearTimeout(clearTimeoutId)
})
</script>
<template lang="pug">
.container
	h1 {{ props.eventName }}

	CheckinlistSelect(v-if="!checkinlist", @selected="selectList")

	input.form-control.scan-input(
		v-if="checkinlist",
		ref="inputEl",
		v-model="query",
		:placeholder="STRINGS['input.placeholder']",
		@keyup="inputKeyup"
	)

	.panel.panel-primary.check-result(v-if="checkResult !== null")
		.panel-heading
			a.pull-right(href="#", tabindex="-1", @click.prevent="clear")
				span.fa.fa-close
			h3.panel-title {{ STRINGS['check.headline'] }}
		.panel-body.text-center(v-if="checkLoading")
			span.fa.fa-4x.fa-cog.fa-spin.loading-icon
		.panel-body.text-center(v-else-if="checkError") {{ checkError }}
		.check-result-status(:class="'check-result-' + checkResultColor")
			.check-result-text {{ checkResultText }}
			.check-result-item {{ checkResultItemvar }}
			.check-result-reason(v-if="checkResult.reason_explanation") {{ checkResult.reason_explanation }}
		.attention(v-if="checkResult && checkResult.require_attention")
			span.fa.fa-warning
			| {{ STRINGS['check.attention'] }}
		.panel-body(v-if="checkResult.position")
			.details
				code {{ checkResult.position.order }}-{{ checkResult.position.positionid }}
				h4 {{ checkResult.position.attendee_name }}
				.addons(v-if="checkResultAddons") {{ checkResultAddons }}
				span(v-if="checkResultSubevent") {{ checkResultSubevent }}
					br
				span.secret {{ checkResult.position.secret }}
				span(v-if="checkResult.position.seat")
					br
					| {{ checkResult.position.seat.name }}
				span(v-for="a in checkResult.position.answers")
					span(v-if="a.question.show_during_checkin")
						br
						strong {{ i18nstringLocalize(a.question.question) }}:
						|  {{ formatAnswer(a.answer, a.question) }}
				strong(v-for="t in checkResult.checkin_texts")
					br
					| {{ t }}

	.panel.panel-primary.search-results(v-else-if="searchResults !== null")
		.panel-heading
			a.pull-right(href="#", tabindex="-1", @click.prevent="clear")
				span.fa.fa-close
			h3.panel-title {{ STRINGS['results.headline'] }}
		ul.list-group
			SearchresultItem(
				v-for="(p, idx) in searchResults",
				:ref="el => { if (el) resultEls[idx] = el }",
				:key="p.id",
				:position="p",
				@selected="selectResult"
			)
			li.list-group-item.text-center(v-if="!searchResults.length && !searchLoading")
				| {{ STRINGS['results.none'] }}
			li.list-group-item.text-center(v-if="searchLoading")
				span.fa.fa-4x.fa-cog.fa-spin.loading-icon
			li.list-group-item.text-center(v-else-if="searchError") {{ searchError }}
			a.list-group-item.text-center(v-else-if="searchNextUrl", href="#", @click.prevent="searchNext")
				| {{ STRINGS['pagination.next'] }}

	div(v-else-if="checkinlist")
		.panel.panel-default
			.panel-body.meta
				.row.settings
					.col-sm-6
						div
							span.fa(:class="'fa-sign-' + (type === 'exit' ? 'out' : 'in')")
							|  {{ STRINGS['scantype.' + type] }}
							br
							button.btn.btn-default(@click="switchType")
								span.fa.fa-refresh
								|  {{ STRINGS['scantype.switch'] }}
					.col-sm-6
						div(v-if="checkinlist")
							| {{ checkinlist.name }}
							br
							template(v-if="subevent")
								| {{ subevent }}
								br
							button.btn.btn-default(type="button", @click="switchList")
								| {{ STRINGS['checkinlist.switch'] }}
				.row.status(v-if="status")
					.col-sm-4
						span.statistic {{ status.checkin_count }}
						|  {{ STRINGS['status.checkin'] }}
					.col-sm-4
						span.statistic {{ status.position_count }}
						|  {{ STRINGS['status.position'] }}
					.col-sm-4
						.pull-right
							button.btn.btn-default(@click="fetchStatus")
								span.fa.fa-refresh(:class="{ 'fa-spin': statusLoading }")
						span.statistic {{ status.inside_count }}
						|  {{ STRINGS['status.inside'] }}

	.modal.modal-unpaid.fade(:class="{ in: showUnpaidModal }", tabindex="-1", role="dialog")
		.modal-dialog(role="document")
			.modal-content(v-if="checkResult && checkResult.position")
				.modal-header
					button.close(type="button", @click="showUnpaidModal = false")
						span.fa.fa-close
					h4.modal-title {{ STRINGS['modal.unpaid.head'] }}
				.modal-body
					p {{ STRINGS['modal.unpaid.text'] }}
				.modal-footer
					button.btn.btn-primary.pull-right(
						type="button",
						@click="check(checkResult.position.secret, true, false, false, true)"
					) {{ STRINGS['modal.continue'] }}
					button.btn.btn-default(type="button", @click="showUnpaidModal = false")
						| {{ STRINGS['modal.cancel'] }}

	form.modal.modal-questions.fade(
		ref="questionsModalEl",
		:class="{ in: showQuestionsModal }",
		tabindex="-1",
		role="dialog"
	)
		.modal-dialog(role="document")
			.modal-content(v-if="checkResult && checkResult.questions")
				.modal-header
					button.close(type="button", @click="showQuestionsModal = false")
						span.fa.fa-close
					h4.modal-title {{ STRINGS['modal.questions'] }}
				.modal-body
					div(
						v-for="q in checkResult.questions",
						:class="q.type === 'M' ? '' : (q.type === 'B' ? 'checkbox' : 'form-group')"
					)
						label(v-if="q.type !== 'B'", :for="'q_' + q.id")
							| {{ q.question }}
							| {{ q.required ? ' *' : '' }}

						textarea.form-control(
							v-if="q.type === 'T'",
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							:required="q.required"
						)
						input.form-control(
							v-else-if="q.type === 'N'",
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							type="number",
							:required="q.required"
						)
						Datefield(
							v-else-if="q.type === 'D'",
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							:required="q.required"
						)
						Timefield(
							v-else-if="q.type === 'H'",
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							:required="q.required"
						)
						Datetimefield(
							v-else-if="q.type === 'W'",
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							:required="q.required"
						)
						select.form-control(
							v-else-if="q.type === 'C'",
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							:required="q.required"
						)
							option(v-if="!q.required")
							option(v-for="op in q.options", :value="op.id.toString()") {{ op.answer }}
						div(v-else-if="q.type === 'F'")
							em file input not supported
						div(v-else-if="q.type === 'M'")
							.checkbox(v-for="op in q.options")
								label
									input(
										type="checkbox",
										:checked="answers[q.id.toString()] && answers[q.id.toString()].split(',').includes(op.id.toString())",
										@input="answerSetM(q.id.toString(), op.id.toString(), $event.target.checked)"
									)
									|  {{ op.answer }}
						label(v-else-if="q.type === 'B'")
							input(
								type="checkbox",
								:checked="answers[q.id.toString()] === 'true'",
								:required="q.required",
								@input="answers[q.id.toString()] = $event.target.checked.toString()"
							)
							|  {{ q.question }}
							| {{ q.required ? ' *' : '' }}
						select.form-control(
							v-else-if="q.type === 'CC'",
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							:required="q.required"
						)
							option(v-if="!q.required")
							option(v-for="op in COUNTRIES", :value="op.key") {{ op.value }}
						input.form-control(
							v-else,
							:id="'q_' + q.id",
							v-model="answers[q.id.toString()]",
							:required="q.required"
						)
				.modal-footer
					button.btn.btn-primary.pull-right(
						type="button",
						@click="check(checkResult.position.secret, true, true, false, false)"
					) {{ STRINGS['modal.continue'] }}
					button.btn.btn-default(type="button", @click="showQuestionsModal = false")
						| {{ STRINGS['modal.cancel'] }}
</template>
