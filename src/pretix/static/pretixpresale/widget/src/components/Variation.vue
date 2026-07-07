<script setup lang="ts">
import { computed, inject } from 'vue'
import type { Variation, Item, Category } from '~/types'
import { StoreKey } from '~/sharedStore'
import { STRINGS, interpolate } from '~/i18n'
import AvailBox from './AvailBox.vue'
import PriceBox from './PriceBox.vue'

const props = defineProps<{
	variation: Variation
	item: Item
	category: Category
}>()

const store = inject(StoreKey)!

const origPrice = computed(() => props.variation.original_price || props.item.original_price)

const quotaLeftStr = computed(() => interpolate(STRINGS.quota_left, [props.variation.avail[1]]))

const variationLabelId = computed(() => `${store.htmlId}-variation-label-${props.item.id}-${props.variation.id}`)

const variationDescId = computed(() => `${store.htmlId}-variation-desc-${props.item.id}-${props.variation.id}`)

const variationPriceId = computed(() => `${store.htmlId}-variation-price-${props.item.id}-${props.variation.id}`)

const ariaLabelledby = computed(() => `${variationLabelId.value} ${variationPriceId.value}`)

const headingLevel = computed(() => props.category.name ? '5' : '4')

const showQuotaLeft = computed(() => props.variation.avail[1] !== null && props.variation.avail[0] === 100)

// TODO dedupe?
const showPrices = computed(() => {
	// Determine if prices should be shown
	let hasPriced = false
	let cntItems = 0
	for (const cat of store.categories) {
		for (const item of cat.items) {
			if (item.has_variations) {
				cntItems += item.variations.length
				hasPriced = true
			} else {
				cntItems++
				hasPriced = hasPriced || item.price.gross !== '0.00' || item.free_price
			}
		}
	}
	return hasPriced || cntItems > 1
})
</script>
<template lang="pug">
.pretix-widget-variation(
	:data-id="variation.id",
	role="group",
	:aria-labelledby="ariaLabelledby",
	:aria-describedby="variationDescId"
)
	.pretix-widget-item-row
		//- Variation description
		.pretix-widget-item-info-col
			.pretix-widget-item-title-and-description
				strong.pretix-widget-item-title(
					:id="variationLabelId",
					role="heading",
					:aria-level="headingLevel"
				) {{ variation.value }}
				.pretix-widget-item-description(
					v-if="variation.description",
					:id="variationDescId",
					v-html="variation.description"
				)
				p.pretix-widget-item-meta(v-if="showQuotaLeft")
					small {{ quotaLeftStr }}

		//- Price
		.pretix-widget-item-price-col(:id="variationPriceId")
			PriceBox(
				v-if="showPrices",
				:price="variation.price",
				:freePrice="item.free_price",
				:originalPrice="origPrice",
				:mandatoryPricedAddons="item.mandatory_priced_addons",
				:suggestedPrice="variation.suggested_price",
				:fieldName="`price_${item.id}_${variation.id}`",
				:itemId="item.id"
			)
			span(v-if="!showPrices") &nbsp;

		//- Availability
		.pretix-widget-item-availability-col
			AvailBox(:item="item", :variation="variation")

		.pretix-widget-clear
</template>
<style lang="sass">
</style>
