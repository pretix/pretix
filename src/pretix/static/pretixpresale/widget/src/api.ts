import type { Category, DayEntry, EventEntry, MetaFilterField } from '~/types'

export class ApiError extends Error {
	status: number
	responseUrl: string

	constructor (status: number, responseUrl: string) {
		super(`HTTP ${status}`)
		this.status = status
		this.responseUrl = responseUrl
	}
}

// --- Product list ---

export interface ProductListResponse {
	target_url?: string
	subevent?: string | number
	name?: string
	frontpage_text?: string
	date_range?: string
	location?: string
	items_by_category?: Category[]
	currency?: string
	display_net_prices?: boolean
	voucher_explanation_text?: string
	error?: string
	display_add_to_cart?: boolean
	waiting_list_enabled?: boolean
	show_variations_expanded?: boolean
	cart_exists?: boolean
	vouchers_exist?: boolean
	has_seating_plan?: boolean
	has_seating_plan_waitinglist?: boolean
	itemnum?: number
	poweredby?: string
	events?: EventEntry[]
	has_more_events?: boolean
	meta_filter_fields?: MetaFilterField[]
	weeks?: DayEntry[][]
	date?: string
	days?: DayEntry[]
	week?: [number, number]
}

export async function fetchProductList (url: string) {
	const response = await fetch(url)
	if (!response.ok) {
		throw new ApiError(response.status, response.url)
	}
	return {
		data: await response.json() as ProductListResponse,
		responseUrl: response.url,
	}
}

export interface CartResponse {
	redirect?: string
	cart_id?: string
	success?: boolean
	message?: string
	has_cart?: boolean
	async_id?: string
	check_url?: string
}

export async function submitCart (endpoint: string, formData: FormData) {
	const response = await fetch(endpoint, {
		method: 'POST',
		headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
		body: new URLSearchParams(formData as any).toString(),
	})
	if (!response.ok) {
		throw new ApiError(response.status, response.url)
	}
	return await response.json() as CartResponse
}

export async function checkAsyncTask (url: string) {
	const response = await fetch(url)
	if (!response.ok) {
		throw new ApiError(response.status, response.url)
	}
	return await response.json() as CartResponse
}
