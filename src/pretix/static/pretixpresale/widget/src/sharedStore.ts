import { nextTick, type InjectionKey } from 'vue'
import { createStore } from '~/lib/store'
import { fetchProductList, submitCart, checkAsyncTask, ApiError } from '~/api'
import type { CartResponse } from '~/api'
import { STRINGS } from '~/i18n'
import { setCookie, getCookie, makeid } from '~/utils'
import type { Category, DayEntry, EventEntry, LightboxState, MetaFilterField, WidgetData } from '~/types'

export const globalWidgetId = makeid(16)

export type WidgetStore = ReturnType<typeof createWidgetStore>
export const StoreKey: InjectionKey<WidgetStore> = Symbol('WidgetStore')

export function createWidgetStore (config: {
	targetUrl: string
	isButton?: boolean
	voucher?: string | null
	subevent?: string | number | null
	listType?: string | null
	skipSsl?: boolean
	disableIframe?: boolean
	disableVouchers?: boolean
	disableFilters?: boolean
	displayEventInfo?: boolean | null
	filter?: string | null
	items?: string | null
	categories?: string | null
	variations?: string | null
	widgetData: WidgetData
	htmlId: string
	// Button-specific
	buttonItems?: { item: string; count: string }[]
	buttonText?: string
}) {
	return createStore({
		state: () => ({
			// Target/URL state
			targetUrl: config.targetUrl,
			parentStack: [] as string[],
			subevent: config.subevent ?? null as string | number | null,

			// Configuration
			voucherCode: config.voucher ?? null as string | null,
			skipSsl: config.skipSsl ?? false,
			disableIframe: config.disableIframe ?? false,
			disableVouchers: config.disableVouchers ?? false,
			disableFilters: config.disableFilters ?? false,
			displayEventInfo: config.displayEventInfo ?? null as boolean | null,
			filter: config.filter ?? null as string | null,
			itemFilter: config.items ?? null as string | null,
			categoryFilter: config.categories ?? null as string | null,
			variationFilter: config.variations ?? null as string | null,
			style: config.listType ?? null as string | null,
			widgetData: config.widgetData,
			widgetId: `pretix-widget-${globalWidgetId}`,
			htmlId: config.htmlId,

			// View state
			view: null as 'event' | 'events' | 'weeks' | 'days' | null,
			loading: config.isButton ? 0 : 1,
			error: null as string | null,
			connectionError: false,
			frameDismissed: false,

			// Event data
			name: null as string | null,
			dateRange: null as string | null,
			location: null as string | null,
			frontpageText: null as string | null,
			categories: [] as Category[],
			currency: '',
			displayNetPrices: false,
			voucherExplanationText: null as string | null,
			displayAddToCart: false,
			waitingListEnabled: false,
			showVariationsExpanded: !!config.variations,
			cartId: null as string | null,
			cartExists: false,
			vouchersExist: false,
			hasSeatingPlan: false,
			hasSeatingPlanWaitinglist: false,
			itemnum: 0,
			poweredby: '',

			// Calendar/list data
			events: null as EventEntry[] | null,
			weeks: null as DayEntry[][] | null,
			days: null as DayEntry[] | null,
			date: null as string | null,
			week: null as [number, number] | null,
			hasMoreEvents: false,
			offset: 0,
			appendEvents: false,
			metaFilterFields: [] as MetaFilterField[],

			// UI state
			mobile: false,

			// Button-specific
			isButton: config.isButton ?? false,
			items: (config.buttonItems ?? []) as { item: string; count: string }[],
			buttonText: config.buttonText ?? '',

			// Overlay (always initialized, no null guards)
			overlay: {
				frameSrc: '',
				frameLoading: false,
				frameShown: false,
				errorMessage: null as string | null,
				errorUrlAfter: null as string | null,
				errorUrlAfterNewTab: false,
				lightbox: null as LightboxState | null,
			},

			// Async task state
			asyncTaskId: null as string | null,
			asyncTaskCheckUrl: null as string | null,
			asyncTaskTimeout: null as ReturnType<typeof setTimeout> | null,
			asyncTaskInterval: 100,
			voucher: null as string | null,
		}),

		getters: {
			useIframe (): boolean {
				if ((window as any).crossOriginIsolated === true) return false
				return !this.disableIframe && (this.skipSsl || /https.*/.test(document.location.protocol))
			},
			cookieName (): string {
				return `pretix_widget_${this.targetUrl.replace(/[^a-zA-Z0-9]+/g, '_')}`
			},
			cartIdFromCookie (): string | null {
				return getCookie(this.cookieName) ?? null
			},
			widgetDataJson (): string {
				const cloned = { ...this.widgetData }
				delete cloned.consent
				return JSON.stringify(cloned)
			},
			consentParameter (): string {
				if (this.widgetData.consent) {
					return `&consent=${encodeURIComponent(this.widgetData.consent)}`
				}
				return ''
			},
			additionalURLParams (): string {
				if (!window.location.search.includes('utm_')) {
					return ''
				}
				const params = new URLSearchParams(window.location.search)
				for (const [key] of params.entries()) {
					if (!key.startsWith('utm_')) {
						params.delete(key)
					}
				}
				return params.toString()
			},
			newTabTarget (): string {
				return this.subevent ? `${this.targetUrl}${this.subevent}/` : this.targetUrl
			},
			formTarget (): string {
				const isFirefox = navigator.userAgent.toLowerCase().includes('firefox')
				const isAndroid = navigator.userAgent.toLowerCase().includes('android')
				if (isAndroid && isFirefox) {
					return '_top'
				}
				return '_blank'
			},
			consentParameterValue (): string {
				if (this.widgetData.consent) {
					return encodeURIComponent(this.widgetData.consent)
				}
				return ''
			},
			formAction (): string {
				if (!this.useIframe && this.isButton && this.items.length === 0) {
					if (this.voucherCode) return `${this.targetUrl}redeem`
					if (this.subevent) return `${this.targetUrl}${this.subevent}/`
					return this.targetUrl
				}

				let checkoutUrl = `/${this.targetUrl.replace(/^[^/]+:\/\/([^/]+)\//, '')}w/${globalWidgetId}/`
				if (!this.cartExists) {
					checkoutUrl += 'checkout/start'
				}
				if (this.additionalURLParams) {
					checkoutUrl += `?${this.additionalURLParams}`
				}

				let formTarget = `${this.targetUrl}w/${globalWidgetId}/cart/add?iframe=1&next=${encodeURIComponent(checkoutUrl)}`
				if (this.cartIdFromCookie) {
					formTarget += `&take_cart_id=${this.cartIdFromCookie}`
				}
				formTarget += this.consentParameter
				return formTarget
			},
		},
		actions: {
			triggerLoadCallback () {
				nextTick(() => {
					for (const callback of (window as any).PretixWidget._loaded || []) {
						callback()
					}
				})
			},
			async reload (opt: { focus?: string } = {}) {
				if (this.isButton) return

				let url: string
				if (this.subevent) {
					url = `${this.targetUrl}${this.subevent}/widget/product_list?lang=${LANG}`
				} else {
					url = `${this.targetUrl}widget/product_list?lang=${LANG}`
				}

				if (this.offset) url += `&offset=${this.offset}`
				if (this.filter) url += `&${this.filter}`
				if (this.itemFilter) url += `&items=${encodeURIComponent(this.itemFilter)}`
				if (this.categoryFilter) url += `&categories=${encodeURIComponent(this.categoryFilter)}`
				if (this.variationFilter) url += `&variations=${encodeURIComponent(this.variationFilter)}`
				if (this.voucherCode) url += `&voucher=${encodeURIComponent(this.voucherCode)}`

				const cartIdCookie = this.cartIdFromCookie
				if (cartIdCookie) url += `&cart_id=${encodeURIComponent(cartIdCookie)}`
				if (this.date !== null) {
					url += `&date=${this.date.substring(0, 7)}`
				} else if (this.week !== null) {
					url += `&date=${this.week[0]}-W${this.week[1]}`
				}
				if (this.style !== null) url += `&style=${encodeURIComponent(this.style)}`

				try {
					const { data, responseUrl } = await fetchProductList(url)

					// Check for redirect
					const newUrl = responseUrl.substring(0, responseUrl.indexOf('/widget/product_list?') + 1)
					const oldUrl = url.substring(0, url.indexOf('/widget/product_list?') + 1)
					if (newUrl !== oldUrl) {
						let adjustedUrl = newUrl
						if (this.subevent) {
							adjustedUrl = adjustedUrl.substring(0, adjustedUrl.lastIndexOf('/', adjustedUrl.length - 1) + 1)
						}
						this.targetUrl = adjustedUrl
						this.reload()
						return
					}

					this.connectionError = false

					if (data.weeks !== undefined) {
						this.weeks = data.weeks
						this.date = data.date ?? null
						this.week = null
						this.events = null
						this.view = 'weeks'
						this.name = data.name ?? null
						this.frontpageText = data.frontpage_text ?? null
						this.metaFilterFields = data.meta_filter_fields ?? []
					} else if (data.days !== undefined) {
						this.days = data.days
						this.date = null
						this.week = data.week ?? null
						this.events = null
						this.view = 'days'
						this.name = data.name ?? null
						this.frontpageText = data.frontpage_text ?? null
						this.metaFilterFields = data.meta_filter_fields ?? []
					} else if (data.events !== undefined) {
						this.events = this.appendEvents && this.events
							? this.events.concat(data.events)
							: data.events
						this.appendEvents = false
						this.weeks = null
						this.view = 'events'
						this.name = data.name ?? null
						this.frontpageText = data.frontpage_text ?? null
						this.hasMoreEvents = data.has_more_events ?? false
						this.metaFilterFields = data.meta_filter_fields ?? []
					} else {
						this.view = 'event'
						this.targetUrl = data.target_url ?? this.targetUrl
						this.subevent = data.subevent ?? null
						this.name = data.name ?? null
						this.frontpageText = data.frontpage_text ?? null
						this.dateRange = data.date_range ?? null
						this.location = data.location ?? null
						this.categories = data.items_by_category ?? []
						this.currency = data.currency ?? ''
						this.displayNetPrices = data.display_net_prices ?? false
						this.voucherExplanationText = data.voucher_explanation_text ?? null
						this.error = data.error ?? null
						this.displayAddToCart = data.display_add_to_cart ?? false
						this.waitingListEnabled = data.waiting_list_enabled ?? false
						this.showVariationsExpanded = data.show_variations_expanded || !!this.variationFilter
						this.cartId = cartIdCookie
						this.cartExists = data.cart_exists ?? false
						this.vouchersExist = data.vouchers_exist ?? false
						this.hasSeatingPlan = data.has_seating_plan ?? false
						this.hasSeatingPlanWaitinglist = data.has_seating_plan_waitinglist ?? false
						this.itemnum = data.itemnum ?? 0
					}

					this.poweredby = data.poweredby ?? ''

					if (this.loading > 0) {
						this.loading--
						this.triggerLoadCallback()
					}

					// Auto-open seating plan if applicable
					if (
						this.parentStack.length > 0
						&& this.hasSeatingPlan
						&& this.categories.length === 0
						&& !this.frameDismissed
						&& this.useIframe
						&& !this.error
						&& !this.hasSeatingPlanWaitinglist
					) {
						this.startseating()
					} else if (opt.focus) {
						nextTick(() => {
							document.querySelector<HTMLElement>(opt.focus!)?.focus()
						})
					}
				} catch (e) {
					this.categories = []
					this.currency = ''
					if (e instanceof ApiError && e.status === 429) {
						this.error = STRINGS.loading_error_429
					} else {
						this.error = STRINGS.loading_error
					}
					this.connectionError = true
					if (this.loading > 0) {
						this.loading--
						this.triggerLoadCallback()
					}
				}
			},
			getVoucherFormTarget (): string {
				let formTarget = `${this.targetUrl}w/${globalWidgetId}/redeem?iframe=1&locale=${LANG}`
				if (this.cartIdFromCookie) {
					formTarget += `&take_cart_id=${this.cartIdFromCookie}`
				}
				if (this.subevent) {
					formTarget += `&subevent=${this.subevent}`
				}
				if (this.widgetData) {
					formTarget += `&widget_data=${encodeURIComponent(this.widgetDataJson)}`
				}
				formTarget += this.consentParameter
				if (this.additionalURLParams) {
					formTarget += `&${this.additionalURLParams}`
				}
				return formTarget
			},
			handleCartResponse (data: CartResponse) {
				if (data.redirect) {
					if (data.cart_id) {
						this.cartId = data.cart_id
						setCookie(this.cookieName, data.cart_id, 30)
					}

					let url = data.redirect
					if (url.substring(0, 1) === '/') {
						url = `${this.targetUrl.replace(/^([^/]+:\/\/[^/]+)\/.*$/, '$1')}${url}`
					}

					if (url.includes('?')) {
						url = `${url}&iframe=1&locale=${LANG}&take_cart_id=${this.cartId}`
					} else {
						url = `${url}?iframe=1&locale=${LANG}&take_cart_id=${this.cartId}`
					}
					url += this.consentParameter
					if (this.additionalURLParams) {
						url += `&${this.additionalURLParams}`
					}

					if (data.success === false) {
						url = url.replace(/checkout\/start/g, '')
						this.overlay.errorMessage = data.message ?? null
						if (data.has_cart) {
							this.overlay.errorUrlAfter = url
						}
						this.overlay.frameLoading = false
					} else {
						this.overlay.frameSrc = url
					}
				} else {
					this.asyncTaskId = data.async_id
					if (data.check_url) {
						this.asyncTaskCheckUrl = `${this.targetUrl.replace(/^([^/]+:\/\/[^/]+)\/.*$/, '$1')}${data.check_url}`
					}
					this.asyncTaskTimeout = window.setTimeout(() => this.pollAsyncTask(), this.asyncTaskInterval)
					this.asyncTaskInterval = 250
				}
			},
			async pollAsyncTask () {
				if (!this.asyncTaskCheckUrl) return
				try {
					const data = await checkAsyncTask(this.asyncTaskCheckUrl)
					this.handleCartResponse(data)
				} catch (e) {
					if (e instanceof ApiError && (e.status === 200 || (e.status >= 400 && e.status < 500))) {
						this.overlay.errorMessage = STRINGS.cart_error
						this.overlay.frameLoading = false
					} else {
						this.asyncTaskTimeout = window.setTimeout(() => this.pollAsyncTask(), 1000)
					}
				}
			},
			async buy (formData: FormData, event?: Event) {
				if (!this.useIframe) return
				if (event) event.preventDefault()

				if (this.isButton && this.items.length === 0) {
					if (this.voucherCode) {
						this.voucherOpen(this.voucherCode)
					} else {
						this.resume()
					}
					return
				}

				const url = `${this.formAction}&locale=${LANG}&ajax=1`
				this.overlay.frameLoading = true
				this.asyncTaskInterval = 100

				try {
					const data = await submitCart(url, formData)
					this.handleCartResponse(data)
				} catch (e) {
					if (e instanceof ApiError) {
						if (e.status === 429) {
							this.overlay.errorMessage = STRINGS.cart_error_429
							this.overlay.frameLoading = false
							this.overlay.errorUrlAfter = this.newTabTarget
							this.overlay.errorUrlAfterNewTab = true
						} else if (e.status === 405) {
							// Likely a redirect!
							this.targetUrl = e.responseUrl.substring(0, e.responseUrl.indexOf('/cart/add') - 18)
							this.overlay.frameLoading = false
							this.buy(formData)
							return
						}
					}
					this.overlay.errorMessage = STRINGS.cart_error
					this.overlay.frameLoading = false
				}
			},
			redeem (voucherCode: string, event?: Event) {
				if (!this.useIframe) return
				if (event) event.preventDefault()
				this.voucherOpen(voucherCode)
			},
			voucherOpen (voucherCode: string) {
				// TODO just use https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams
				const redirectUrl = `${this.getVoucherFormTarget()}&voucher=${encodeURIComponent(voucherCode)}`
				if (this.useIframe) {
					this.overlay.frameSrc = redirectUrl
				} else {
					window.open(redirectUrl)
				}
			},
			resume () {
				let redirectUrl = `${this.targetUrl}w/${globalWidgetId}/`
				if (this.subevent && !this.cartId) {
					// button with subevent but no items
					redirectUrl += `${this.subevent}/`
				}
				redirectUrl += `?iframe=1&locale=${LANG}`
				if (this.cartId) {
					redirectUrl += `&take_cart_id=${this.cartId}`
				}
				if (this.widgetData) {
					redirectUrl += `&widget_data=${encodeURIComponent(this.widgetDataJson)}`
				}
				redirectUrl += this.consentParameter
				if (this.additionalURLParams) {
					redirectUrl += `&${this.additionalURLParams}`
				}
				if (this.useIframe) {
					this.overlay.frameSrc = redirectUrl
				} else {
					window.open(redirectUrl)
				}
			},
			startwaiting () {
				let redirectUrl = `${this.targetUrl}w/${globalWidgetId}/waitinglist/?iframe=1&locale=${LANG}`
				if (this.subevent) {
					redirectUrl += `&subevent=${this.subevent}`
				}
				if (this.additionalURLParams) {
					redirectUrl += `&${this.additionalURLParams}`
				}
				if (this.useIframe) {
					this.overlay.frameSrc = redirectUrl
				} else {
					window.open(redirectUrl)
				}
			},
			startseating () {
				let redirectUrl = `${this.targetUrl}w/${globalWidgetId}`
				if (this.subevent) {
					redirectUrl += `/${this.subevent}`
				}
				redirectUrl += `/seatingframe/?iframe=1&locale=${LANG}`
				if (this.voucherCode) {
					redirectUrl += `&voucher=${encodeURIComponent(this.voucherCode)}`
				}
				if (this.cartId) {
					redirectUrl += `&take_cart_id=${this.cartId}`
				}
				if (this.widgetData) {
					redirectUrl += `&widget_data=${encodeURIComponent(this.widgetDataJson)}`
				}
				redirectUrl += this.consentParameter
				if (this.additionalURLParams) {
					redirectUrl += `&${this.additionalURLParams}`
				}
				if (this.useIframe) {
					this.overlay.frameSrc = redirectUrl
				} else {
					window.open(redirectUrl)
				}
			}
		}
	})
}
