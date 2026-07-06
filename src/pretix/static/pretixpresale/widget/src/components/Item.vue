<script setup lang="ts">
import { computed, inject, ref, watch, onMounted } from 'vue'
import type { Item, Category } from '~/types'
import { StoreKey } from '~/sharedStore'
import { STRINGS, interpolate } from '~/i18n'
import { floatformat } from '~/utils'
import AvailBox from './AvailBox.vue'
import PriceBox from './PriceBox.vue'
import Variation from './Variation.vue'

const props = defineProps<{
	item: Item
	category: Category
}>()

const store = inject(StoreKey)!

const expanded = ref(store.showVariationsExpanded)
const variations = ref<HTMLDivElement>()

const classObject = computed(() => ({
	'pretix-widget-item': true,
	'pretix-widget-item-with-picture': !!props.item.picture,
	'pretix-widget-item-with-variations': props.item.has_variations,
}))

const varClasses = computed(() => ({
	'pretix-widget-item-variations': true,
	'pretix-widget-item-variations-expanded': expanded.value,
}))

const pictureAltText = computed(() => interpolate(STRINGS.image_of, [props.item.name]))

const headingLevel = computed(() => props.category.name ? '4' : '3')

const itemLabelId = computed(() => `${store.htmlId}-item-label-${props.item.id}`)

const itemDescId = computed(() => `${store.htmlId}-item-desc-${props.item.id}`)

const itemPriceId = computed(() => `${store.htmlId}-item-price-${props.item.id}`)

const ariaLabelledby = computed(() => `${itemLabelId.value} ${itemPriceId.value}`)

const minOrderStr = computed(() => interpolate(STRINGS.order_min, [props.item.order_min]))

const quotaLeftStr = computed(() => interpolate(STRINGS.quota_left, [props.item.avail[1]]))

const showToggle = computed(() => props.item.has_variations && !store.showVariationsExpanded)

// TODO dedupe?
const showPrices = computed(() => {
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

// TODO XSS
const pricerange = computed(() => {
	if (props.item.free_price) {
		return interpolate(
			STRINGS.price_from,
			{
				currency: store.currency,
				price: floatformat(props.item.min_price || '0', 2),
			},
			true
		).replace(
			store.currency,
			`<span class="pretix-widget-pricebox-currency">${store.currency}</span>`
		)
	} else if (props.item.min_price !== props.item.max_price) {
		return `<span class="pretix-widget-pricebox-currency">${store.currency}</span> ${floatformat(props.item.min_price || '0', 2)} – ${floatformat(props.item.max_price || '0', 2)}`
	} else if (props.item.min_price === '0.00' && props.item.max_price === '0.00') {
		if (props.item.mandatory_priced_addons) {
			return '\xA0' // nbsp, because an empty string would cause the HTML element to collapse
		}
		return STRINGS.free
	} else {
		return `<span class="pretix-widget-pricebox-currency">${store.currency}</span> ${floatformat(props.item.min_price || '0', 2)}`
	}
})

const variationsToggleLabel = computed(() => expanded.value ? STRINGS.hide_variations : STRINGS.variations)

function expand () {
	expanded.value = !expanded.value
}

function lightbox () {
	if (store.overlay) {
		store.overlay.lightbox = {
			image: props.item.picture_fullsize || '',
			description: props.item.name,
			loading: true, // TODO why?
		}
	}
}

onMounted(() => {
	if (variations.value && !expanded.value) {
		variations.value.hidden = true

		variations.value.addEventListener('transitionend', function (event) {
			if (event.target === variations.value) {
				if (variations.value) {
					variations.value.hidden = !expanded.value
					variations.value.style.maxHeight = 'none'
				}
			}
		})
	}
})

watch(expanded, (newValue) => {
	const v = variations.value
	if (!v) return

	v.hidden = false
	v.style.maxHeight = `${newValue ? 0 : v.scrollHeight}px`

	// Vue.nextTick does not work here
	setTimeout(() => {
		v.style.maxHeight = `${!newValue ? 0 : v.scrollHeight}px`
	}, 50)
})
</script>
<template lang="pug">
div(
	:class="classObject",
	:data-id="item.id",
	role="group",
	:aria-labelledby="ariaLabelledby",
	:aria-describedby="itemDescId"
)
	.pretix-widget-item-row.pretix-widget-main-item-row
		//- Product description
		.pretix-widget-item-info-col
			a.pretix-widget-item-picture-link(
				v-if="item.picture",
				:href="item.picture_fullsize",
				@click.prevent.stop="lightbox"
			)
				img.pretix-widget-item-picture(:src="item.picture", :alt="pictureAltText")
			.pretix-widget-item-title-and-description
				strong.pretix-widget-item-title(
					:id="itemLabelId",
					role="heading",
					:aria-level="headingLevel"
				) {{ item.name }}
				.pretix-widget-item-description(
					v-if="item.description",
					:id="itemDescId",
					v-html="item.description"
				)
				p.pretix-widget-item-meta(v-if="item.order_min && item.order_min > 1")
					small {{ minOrderStr }}
				p.pretix-widget-item-meta(
					v-if="!item.has_variations && item.avail[1] !== null && item.avail[0] === 100"
				)
					small {{ quotaLeftStr }}

		//- Price
		.pretix-widget-item-price-col(:id="itemPriceId")
			PriceBox(
				v-if="!item.has_variations && showPrices",
				:price="item.price",
				:freePrice="item.free_price",
				:mandatoryPricedAddons="item.mandatory_priced_addons",
				:suggestedPrice="item.suggested_price",
				:fieldName="`price_${item.id}`",
				:originalPrice="item.original_price",
				:itemId="item.id"
			)
			.pretix-widget-pricebox(v-if="item.has_variations && showPrices", v-html="pricerange")
			span(v-if="!showPrices") &nbsp;

		//- Availability
		.pretix-widget-item-availability-col
			button.pretix-widget-collapse-indicator(
				v-if="showToggle",
				type="button",
				:aria-expanded="expanded ? 'true' : 'false'",
				:aria-controls="`${item.id}-variants`",
				:aria-describedby="itemDescId",
				@click.prevent.stop="expand"
			) {{ variationsToggleLabel }}
			AvailBox(v-if="!item.has_variations", :item="item")

		.pretix-widget-clear

	//- Variations
	div(
		v-if="item.has_variations",
		:id="`${item.id}-variants`",
		ref="variations",
		:class="varClasses"
	)
		Variation(
			v-for="variation in item.variations",
			:key="variation.id",
			:variation="variation",
			:item="item",
			:category="category"
		)
</template>
<style lang="sass">
</style>
