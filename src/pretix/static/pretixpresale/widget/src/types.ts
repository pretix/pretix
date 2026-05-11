// Domain model types for the pretix widget

export interface Price {
	gross: string
	net: string
	rate: string
	name: string
	includes_mixed_tax_rate?: boolean
}

export interface Availability {
	color: 'green' | 'orange' | 'red'
	text?: string
	reason?: string
}

export interface Variation {
	id: number
	value: string
	description?: string
	price: Price
	suggested_price?: Price
	original_price?: string
	avail: [number, number | null]
	order_max: number
	current_unavailability_reason?: string
	allow_waitinglist?: boolean
}

export interface Item {
	id: number
	name: string
	description?: string
	picture?: string
	picture_fullsize?: string
	price: Price
	suggested_price?: Price
	original_price?: string
	avail: [number, number | null]
	order_min?: number
	order_max: number
	has_variations: boolean
	variations: Variation[]
	free_price: boolean
	min_price?: string
	max_price?: string
	mandatory_priced_addons?: boolean
	current_unavailability_reason?: string
	allow_waitinglist?: boolean
}

export interface Category {
	id: number
	name?: string
	description?: string
	items: Item[]
}

export interface EventEntry {
	name: string
	event_url: string
	subevent?: number | string
	date_range: string
	location: string
	time?: string
	continued?: boolean
	availability: Availability
}

export interface DayEntry {
	date: string
	day_formatted: string
	events: EventEntry[]
}

export interface MetaFilterField {
	key: string
	label: string
	choices: [string, string][]
}

export interface LightboxState {
	image: string
	description: string
	loading?: boolean
}

export interface WidgetData {
	referer: string
	consent?: string
	[key: string]: string | undefined
}
