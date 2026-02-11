<script setup lang="ts">
import { computed, inject, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { StoreKey } from '~/sharedStore'
import { STRINGS } from '~/i18n'
import Category from './Category.vue'

const store = inject(StoreKey)!

const form = ref<HTMLFormElement>()
const voucherinput = ref<HTMLInputElement>()
const isItemsSelected = ref(false)
const localVoucher = ref('')

const displayEventInfo = computed(() => store.displayEventInfo || (store.displayEventInfo === null && (store.events || store.weeks || store.days)))

const idVoucherInput = computed(() => `${store.htmlId}-voucher-input`)

const ariaLabelledby = computed(() => `${store.htmlId}-voucher-headline`)

const idCartExistsMsg = computed(() => `${store.htmlId}-cart-exists`)

const buyLabel = computed(() => {
	let allFree = true
	for (const cat of store.categories) {
		for (const item of cat.items) {
			for (const v of item.variations) {
				if (v.price.gross !== '0.00') {
					allFree = false
					break
				}
			}
			if ((item.variations.length === 0 && item.price.gross !== '0.00') || item.mandatory_priced_addons) {
				allFree = false
				break
			}
		}
		if (!allFree) break
	}
	return allFree ? STRINGS.register : STRINGS.buy
})

const hiddenParams = computed(() => {
	const params = new URL(store.getVoucherFormTarget()).searchParams
	params.delete('iframe')
	params.delete('take_cart_id')
	return Array.from(params.entries())
})

const showVoucherForm = computed(() => store.vouchersExist && !store.disableVouchers && !store.voucherCode)

const consentParameterValue = computed(() => {
	if (store.widgetData.consent) {
		return encodeURIComponent(store.widgetData.consent)
	}
	return ''
})

const widgetDataJson = computed(() => {
	const clonedData = { ...store.widgetData }
	if (clonedData.consent) {
		delete clonedData.consent
	}
	return JSON.stringify(clonedData)
})

const formAction = computed(() => {
	const additionalParams = getAdditionalURLParams()
	let checkoutUrl = `/${store.targetUrl.replace(/^[^\/]+:\/\/([^\/]+)\//, '')}w/${store.widgetId.replace('pretix-widget-', '')}/`
	if (!store.cartExists) {
		checkoutUrl += 'checkout/start'
	}
	if (additionalParams) {
		checkoutUrl += `?${additionalParams}`
	}

	const cookieName = `pretix_widget_${store.targetUrl.replace(/[^a-zA-Z0-9]+/g, '_')}`
	const cartIdCookie = document.cookie
		.split('; ')
		.find((row) => row.startsWith(`${cookieName}=`))
		?.split('=')[1] || null

	let formTarget = `${store.targetUrl}w/${store.widgetId.replace('pretix-widget-', '')}/cart/add?iframe=1&next=${encodeURIComponent(checkoutUrl)}`
	if (cartIdCookie) {
		formTarget += `&take_cart_id=${cartIdCookie}`
	}
	if (store.widgetData.consent) {
		formTarget += `&consent=${encodeURIComponent(store.widgetData.consent)}`
	}
	return formTarget
})

const formTarget = computed(() => {
	const isFirefox = navigator.userAgent.toLowerCase().includes('firefox')
	const isAndroid = navigator.userAgent.toLowerCase().includes('android')
	if (isAndroid && isFirefox) {
		return '_top'
	}
	return '_blank'
})

function getAdditionalURLParams (): string {
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
}

function backToList () {
	store.targetUrl = store.parentStack.pop() || store.targetUrl
	store.error = null
	if (!store.subevent) {
		store.name = null
		store.frontpageText = null
	}
	store.subevent = null
	store.offset = 0
	store.appendEvents = false
	store.triggerLoadCallback()

	if (store.events !== null) {
		store.view = 'events'
	} else if (store.days !== null) {
		store.view = 'days'
	} else {
		store.view = 'weeks'
	}
}

function calcItemsSelected () {
	if (!form.value) return
	const checkboxes = form.value.querySelectorAll<HTMLInputElement>('input[type=checkbox], input[type=radio]')
	const hasChecked = Array.from(checkboxes).some((el) => el.checked)
	const numberInputs = form.value.querySelectorAll<HTMLInputElement>('.pretix-widget-item-count-group input')
	const hasQuantity = Array.from(numberInputs).some((el) => parseInt(el.value || '0') > 0)
	isItemsSelected.value = hasChecked || hasQuantity
}

function focusVoucherField () {
	voucherinput.value?.focus()
}

function handleBuy (event: Event) {
	if (form.value) {
		const formData = new FormData(form.value)
		store.buy(formData, event)
	}
}

function handleRedeem (event: Event) {
	store.redeem(localVoucher.value, event)
}

onMounted(() => {
	if (form.value) {
		form.value.addEventListener('change', calcItemsSelected)
	}
})

onBeforeUnmount(() => {
	if (form.value) {
		form.value.removeEventListener('change', calcItemsSelected)
	}
})

watch(() => store.overlay?.frameShown, (newValue) => {
	if (!newValue && form.value) {
		form.value.reset()
		calcItemsSelected()
	}
})
</script>

<template lang="pug">
.pretix-widget-event-form
	//- Back navigation
	.pretix-widget-event-list-back(v-if="store.events || store.weeks || store.days")
		a(v-if="!store.subevent", href="#", rel="back", @click.prevent.stop="backToList")
			| &lsaquo; {{ STRINGS.back_to_list }}
		a(v-if="store.subevent", href="#", rel="back", @click.prevent.stop="backToList")
			| &lsaquo; {{ STRINGS.back_to_dates }}

	//- Event name
	.pretix-widget-event-header(v-if="displayEventInfo")
		strong(role="heading", aria-level="2") {{ store.name }}

	//- Date range
	.pretix-widget-event-details(v-if="displayEventInfo && store.dateRange") {{ store.dateRange }}

	//- Location
	.pretix-widget-event-location(
		v-if="displayEventInfo && store.location",
		v-html="store.location"
	)

	//- Description
	.pretix-widget-event-description(
		v-if="displayEventInfo && store.frontpageText",
		v-html="store.frontpageText"
	)

	//- Form start
	form(
		ref="form",
		method="post",
		:action="formAction",
		:target="formTarget",
		@submit="handleBuy"
	)
		input(v-if="store.voucherCode", type="hidden", name="_voucher_code", :value="store.voucherCode")
		input(type="hidden", name="subevent", :value="store.subevent")
		input(type="hidden", name="widget_data", :value="widgetDataJson")
		input(v-if="consentParameterValue", type="hidden", name="consent", :value="consentParameterValue")

		//- Error message
		.pretix-widget-error-message(v-if="store.error") {{ store.error }}

		//- Resume cart
		.pretix-widget-info-message.pretix-widget-clickable(v-if="store.cartExists")
			span(:id="idCartExistsMsg") {{ STRINGS.cart_exists }}
			button.pretix-widget-resume-button(
				type="button",
				:aria-describedby="idCartExistsMsg",
				@click.prevent.stop="store.resume()"
			) {{ STRINGS.resume_checkout }}

		//- Seating plan
		.pretix-widget-seating-link-wrapper(v-if="store.hasSeatingPlan")
			button.pretix-widget-seating-link(type="button", @click.prevent.stop="store.startseating()")
				| {{ STRINGS.show_seating }}

		//- Waiting list for seating plan
		.pretix-widget-seating-waitinglist(v-if="store.hasSeatingPlan && store.hasSeatingPlanWaitinglist")
			.pretix-widget-seating-waitinglist-text {{ STRINGS.seating_plan_waiting_list }}
			.pretix-widget-seating-waitinglist-button-wrap
				button.pretix-widget-seating-waitinglist-button(@click.prevent.stop="store.startwaiting()")
					| {{ STRINGS.waiting_list }}
			.pretix-widget-clear

		//- Product list
		Category(v-for="category in store.categories", :key="category.id", :category="category")

		//- Buy button
		.pretix-widget-action(v-if="store.displayAddToCart")
			button(
				v-if="!store.cartExists || isItemsSelected",
				type="submit",
				:aria-describedby="idCartExistsMsg"
			) {{ buyLabel }}
			button(
				v-else,
				type="button",
				:aria-describedby="idCartExistsMsg",
				@click.prevent.stop="store.resume()"
			) {{ STRINGS.resume_checkout }}

	//- Voucher form
	form(
		v-if="showVoucherForm",
		method="get",
		:action="store.getVoucherFormTarget()",
		target="_blank"
	)
		.pretix-widget-voucher
			h3.pretix-widget-voucher-headline(:id="ariaLabelledby") {{ STRINGS.redeem_voucher }}
			.pretix-widget-voucher-text(
				v-if="store.voucherExplanationText",
				v-html="store.voucherExplanationText"
			)
			.pretix-widget-voucher-input-wrap
				input.pretix-widget-voucher-input(
					:id="idVoucherInput",
					ref="voucherinput",
					v-model="localVoucher",
					type="text",
					name="voucher",
					:placeholder="STRINGS.voucher_code",
					:aria-labelledby="ariaLabelledby"
				)
			input(
				v-for="p in hiddenParams",
				:key="p[0]",
				type="hidden",
				:name="p[0]",
				:value="p[1]"
			)
			.pretix-widget-voucher-button-wrap
				button(@click="handleRedeem") {{ STRINGS.redeem }}
			.pretix-widget-clear
</template>

<style lang="sass">
</style>
