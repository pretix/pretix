import type { I18nString, SubEvent } from './i18n'

const settingsEl = document.getElementById('api-settings')
const { urls } = JSON.parse(settingsEl.textContent || '{}') as { urls: {
	lists: string
	questions: string
} }

// interfaces generated from api docs
export interface PaginatedResponse<T> {
	count: number
	next: string | null
	previous: string | null
	results: T[]
}

export interface CheckinList {
	id: number
	name: string
	all_products: boolean
	limit_products: number[]
	subevent: SubEvent | null
	position_count?: number
	checkin_count?: number
	include_pending: boolean
	allow_multiple_entries: boolean
	allow_entry_after_exit: boolean
	rules: Record<string, unknown>
	exit_all_at: string | null
	addon_match: boolean
	ignore_in_statistics?: boolean
	consider_tickets_used?: boolean
}

export interface Checkin {
	id: number
	list: number
	datetime: string
	type: 'entry' | 'exit'
	gate: number | null
	device: number | null
	device_id: number | null
	auto_checked_in: boolean
}

export interface Seat {
	id: number
	name: string
	zone_name: string
	row_name: string
	row_label: string | null
	seat_number: string
	seat_label: string | null
	seat_guid: string
}

export interface Position {
	id: number
	order: string
	positionid: number
	canceled?: boolean
	item: { id?: number; name: I18nString; internal_name?: string; admission?: boolean }
	variation: { id?: number; value: I18nString } | null
	price: string
	attendee_name: string
	attendee_name_parts: Record<string, string>
	attendee_email: string | null
	company?: string | null
	street?: string | null
	zipcode?: string | null
	city?: string | null
	country?: string | null
	state?: string | null
	voucher?: number | null
	voucher_budget_use?: string | null
	tax_rate: string
	tax_value: string
	tax_code?: string | null
	tax_rule: number | null
	secret: string
	addon_to: number | null
	subevent: SubEvent | null
	discount?: number | null
	blocked: string[] | null
	valid_from: string | null
	valid_until: string | null
	pseudonymization_id: string
	seat: Seat | null
	checkins: Checkin[]
	downloads?: { output: string; url: string }[]
	answers: Answer[]
	pdf_data?: Record<string, unknown>
	plugin_data?: Record<string, unknown>
	// Additional fields from checkin list positions endpoint
	order__status?: string
	order__valid_if_pending?: boolean
	order__require_approval?: boolean
	order__locale?: string
	require_attention?: boolean
	addons?: Addon[]
}

export interface Answer {
	question: number | AnswerQuestion
	answer: string
	question_identifier: string
	options: number[]
	option_identifiers: string[]
}

export interface AnswerQuestion {
	id: number
	question: I18nString
	help_text?: I18nString
	type: string
	required: boolean
	position: number
	items: number[]
	identifier: string
	ask_during_checkin: boolean
	show_during_checkin: boolean
	hidden?: boolean
	print_on_invoice?: boolean
	options: QuestionOption[]
	valid_number_min?: string | null
	valid_number_max?: string | null
	valid_date_min?: string | null
	valid_date_max?: string | null
	valid_datetime_min?: string | null
	valid_datetime_max?: string | null
	valid_file_portrait?: boolean
	valid_string_length_max?: number | null
	dependency_question?: number | null
	dependency_values?: string[]
}

export interface QuestionOption {
	id: number
	identifier: string
	position: number
	answer: I18nString
}

export interface Addon {
	item: { name: I18nString; internal_name?: string }
	variation: { value: I18nString } | null
}

export interface CheckinStatusVariation {
	id: number
	value: string
	checkin_count: number
	position_count: number
}

export interface CheckinStatusItem {
	id: number
	name: string
	checkin_count: number
	admission: boolean
	position_count: number
	variations: CheckinStatusVariation[]
}

export interface CheckinStatus {
	checkin_count: number
	position_count: number
	inside_count: number
	event?: { name: string }
	items?: CheckinStatusItem[]
}

export interface RedeemRequest {
	questions_supported: boolean
	canceled_supported: boolean
	ignore_unpaid: boolean
	type: 'entry' | 'exit'
	answers: Record<string, string>
	datetime?: string | null
	force?: boolean
	nonce?: string
}

export interface RedeemResponseList {
	id: number
	name: string
	event: string
	subevent: number | null
	include_pending: boolean
}

export interface RedeemResponse {
	status: 'ok' | 'error' | 'incomplete'
	reason?: 'invalid' | 'unpaid' | 'blocked' | 'invalid_time' | 'canceled' | 'already_redeemed' | 'product' | 'rules' | 'ambiguous' | 'revoked' | 'unapproved' | 'error'
	reason_explanation?: string | null
	position?: Position
	questions?: AnswerQuestion[]
	checkin_texts?: string[]
	require_attention?: boolean
	list?: RedeemResponseList
}

const CSRF_TOKEN = document.querySelector<HTMLInputElement>('input[name=csrfmiddlewaretoken]')?.value ?? ''

function handleAuthError (response: Response): void {
	if ([401, 403].includes(response.status)) {
		window.location.href = '/control/login?next=' + encodeURIComponent(
			window.location.pathname + window.location.search + window.location.hash
		)
	}
}

export const api = {
	// generic fetch wrapper, not sure if this should be exposed
	async fetch <T> (url: string, options?: RequestInit): Promise<T> {
		const response = await fetch(url, options)
		handleAuthError(response)
		if (!response.ok && response.status !== 400 && response.status !== 404) {
			throw new Error('HTTP status ' + response.status)
		}
		return response.json()
	},
	async fetchCheckinLists (endsAfter?: string): Promise<PaginatedResponse<CheckinList>> {
		const cutoff = endsAfter ?? moment().subtract(8, 'hours').toISOString()
		const url = `${urls.lists}?exclude=checkin_count&exclude=position_count&expand=subevent&ends_after=${cutoff}`
		return api.fetch(url)
	},
	async fetchCheckinList (listId: string): Promise<CheckinList> {
		return api.fetch(`${urls.lists}${listId}/?expand=subevent`)
	},
	async fetchNextPage<T> (nextUrl: string): Promise<PaginatedResponse<T>> {
		return api.fetch(nextUrl)
	},
	async fetchStatus (listId: number): Promise<CheckinStatus> {
		return api.fetch(`${urls.lists}${listId}/status/`)
	},
	async searchPositions (listId: number, query: string): Promise<PaginatedResponse<Position>> {
		const url = `${urls.lists}${listId}/positions/?ignore_status=true&expand=subevent&expand=item&expand=variation&check_rules=true&search=${encodeURIComponent(query)}`
		return api.fetch(url)
	},
	async redeemPosition (
		listId: number,
		positionId: string,
		data: RedeemRequest,
		untrusted: boolean = false
	): Promise<RedeemResponse> {
		let url = `${urls.lists}${listId}/positions/${encodeURIComponent(positionId)}/redeem/?expand=item&expand=subevent&expand=variation&expand=answers.question&expand=addons`
		if (untrusted) url += '&untrusted_input=true'

		const response = await fetch(url, {
			method: 'POST',
			headers: {
				'X-CSRFToken': CSRF_TOKEN,
				'Content-Type': 'application/json',
			},
			body: JSON.stringify(data),
		})

		handleAuthError(response)

		if (response.status === 404) {
			return { status: 'error', reason: 'invalid' }
		}

		if (!response.ok && response.status !== 400) {
			throw new Error('HTTP status ' + response.status)
		}

		return response.json()
	}
}
