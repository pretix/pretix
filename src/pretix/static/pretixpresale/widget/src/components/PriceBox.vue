<script setup lang="ts">
import { computed, inject } from 'vue'
import type { Price } from '~/types'
import { StoreKey } from '~/sharedStore'
import { STRINGS, interpolate } from '~/i18n'
import { floatformat, autofloatformat, stripHTML } from '~/utils'

const props = defineProps<{
	price: Price
	freePrice: boolean
	fieldName: string
	suggestedPrice?: Price | null
	originalPrice?: string | null
	mandatoryPricedAddons?: boolean
	itemId: number
}>()

const store = inject(StoreKey)!

const priceBoxId = computed(() => `${store.htmlId}-item-pricebox-${props.itemId}`)

const priceDescId = computed(() => `${store.htmlId}-item-pricedesc-${props.itemId}`)

const ariaLabelledby = computed(() => `${store.htmlId}-item-label-${props.itemId} ${priceBoxId.value}`)

const displayPrice = computed(() => {
	if (store.displayNetPrices) {
		return floatformat(parseFloat(props.price.net), 2)
	}
	return floatformat(parseFloat(props.price.gross), 2)
})

const displayPriceNonlocalized = computed(() => {
	if (store.displayNetPrices) {
		return parseFloat(props.price.net).toFixed(2)
	}
	return parseFloat(props.price.gross).toFixed(2)
})

const suggestedPriceNonlocalized = computed(() => {
	const price = props.suggestedPrice ?? props.price
	if (store.displayNetPrices) {
		return parseFloat(price.net).toFixed(2)
	}
	return parseFloat(price.gross).toFixed(2)
})

// TODO BAD
const originalLine = computed(() => {
	if (!props.originalPrice) return ''
	return `<span class="pretix-widget-pricebox-currency">${store.currency}</span> ${floatformat(parseFloat(props.originalPrice), 2)}`
})

// TODO BAD
const priceline = computed(() => {
	if (props.price.gross === '0.00') {
		if (props.mandatoryPricedAddons && !props.originalPrice) {
			return '\u00A0' // nbsp
		}
		return STRINGS.free
	}
	return `<span class="pretix-widget-pricebox-currency">${store.currency}</span> ${displayPrice.value}`
})

const originalPriceAriaLabel = computed(() => interpolate(STRINGS.original_price, [stripHTML(originalLine.value)]))

const newPriceAriaLabel = computed(() => interpolate(STRINGS.new_price, [stripHTML(priceline.value)]))

const taxline = computed(() => {
	if (store.displayNetPrices) {
		if (props.price.includes_mixed_tax_rate) {
			return STRINGS.tax_plus_mixed
		}
		return interpolate(STRINGS.tax_plus, {
			rate: autofloatformat(props.price.rate, 2),
			taxname: props.price.name,
		}, true)
	} else {
		if (props.price.includes_mixed_tax_rate) {
			return STRINGS.tax_incl_mixed
		}
		return interpolate(STRINGS.tax_incl, {
			rate: autofloatformat(props.price.rate, 2),
			taxname: props.price.name,
		}, true)
	}
})

const showTaxline = computed(() => props.price.rate !== '0.00' && props.price.gross !== '0.00')
</script>
<template lang="pug">
.pretix-widget-pricebox
	span(v-if="!freePrice && !originalPrice", v-html="priceline")
	span(v-if="!freePrice && originalPrice")
		del.pretix-widget-pricebox-original-price(:aria-label="originalPriceAriaLabel", v-html="originalLine")
		|
		ins.pretix-widget-pricebox-new-price(:aria-label="newPriceAriaLabel", v-html="priceline")
	div(v-if="freePrice")
		span.pretix-widget-pricebox-currency(:id="priceBoxId") {{ store.currency }}
		|
		input.pretix-widget-pricebox-price-input(
			type="number",
			placeholder="0",
			:min="displayPriceNonlocalized",
			:value="suggestedPriceNonlocalized",
			:name="fieldName",
			step="any",
			:aria-labelledby="ariaLabelledby",
			:aria-describedby="priceDescId"
		)
	small.pretix-widget-pricebox-tax(v-if="showTaxline", :id="priceDescId") {{ taxline }}
</template>
<style lang="sass">
</style>
