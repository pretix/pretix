<script setup lang="ts">
import { computed, ref, inject, onMounted } from 'vue'
import type { Item, Variation } from '~/types'
import { StoreKey, globalWidgetId } from '~/sharedStore'
import { STRINGS } from '~/i18n'

const props = defineProps<{
	item: Item
	variation?: Variation
}>()

const store = inject(StoreKey)!
const quantity = ref<HTMLInputElement>()

const avail = computed(() => props.item.has_variations ? props.variation.avail : props.item.avail)

const orderMax = computed(() => props.item.has_variations ? props.variation.order_max : props.item.order_max)

const inputName = computed(() => {
	if (props.item.has_variations) {
		return `variation_${props.item.id}_${props.variation.id}`
	}
	return `item_${props.item.id}`
})

const unavailabilityReasonMessage = computed(() => {
	const reason = props.item.current_unavailability_reason || props.variation?.current_unavailability_reason
	if (reason) {
		return STRINGS[`unavailable_${reason}`] || reason
	}
	return ''
})

const voucherJumpLink = computed(() => `#${store.htmlId}-voucher-input`)

const ariaLabelledby = computed(() => `${store.htmlId}-item-label-${props.item.id}`)

const decLabel = computed(() => {
	// TODO
	const name = props.item.has_variations ? props.variation.value : props.item.name
	return `- ${name}: ${STRINGS.quantity_dec}`
})

const incLabel = computed(() => {
	const name = props.item.has_variations ? props.variation.value : props.item.name
	return `+ ${name}: ${STRINGS.quantity_inc}`
})

const labelSelectItem = computed(() => {
	if (props.item.has_variations) return STRINGS.select_variant.replace('%s', props.variation.value)
	return STRINGS.select_item.replace('%s', props.item.name)
})

const waitingListShow = computed(() => avail.value[0] < 100 && store.waitingListEnabled && props.item.allow_waitinglist)

const waitingListUrl = computed(() => {
	let u = `${store.targetUrl}w/${globalWidgetId}/waitinglist/?locale=${LANG}&item=${props.item.id}`
	if (props.item.has_variations && props.variation) {
		u += `&var=${props.variation.id}`
	}
	if (store.subevent) {
		u += `&subevent=${store.subevent}`
	}
	const widgetDataJson = JSON.stringify(store.widgetData)
	u += `&widget_data=${encodeURIComponent(widgetDataJson)}`
	if (store.widgetData.consent) {
		u += `&consent=${encodeURIComponent(store.widgetData.consent)}`
	}
	return u
})

function onStep (e: Event) {
	const target = e.target as HTMLElement
	const button = target.tagName === 'BUTTON' ? target : target.closest('button')
	if (!button || !quantity.value) return

	const step = parseFloat(button.getAttribute('data-step') || '0')
	const input = quantity.value
	const min = parseFloat(input.min) || 0
	const max = parseFloat(input.max) || Number.MAX_SAFE_INTEGER
	const currentValue = parseInt(input.value || '0')
	input.value = String(Math.max(min, Math.min(max, currentValue + step)))
	input.dispatchEvent(new CustomEvent('change', { bubbles: true }))
}

onMounted(() => {
	// Auto-select first item if single item with no variations
	if (
		store.itemnum === 1
		&& (!store.categories[0]?.items[0]?.has_variations || store.categories[0]?.items[0]?.variations.length < 2)
		&& !store.hasSeatingPlan
		&& quantity.value
	) {
		quantity.value.value = '1'
		if (orderMax.value === 1 && quantity.value.type === 'checkbox') {
			;(quantity.value as HTMLInputElement).checked = true
		}
	}
})
</script>
<template lang="pug">
.pretix-widget-availability-box
	.pretix-widget-availability-unavailable(v-if="item.current_unavailability_reason === 'require_voucher'")
		small
			a(:href="voucherJumpLink", :aria-describedby="ariaLabelledby") {{ unavailabilityReasonMessage }}
	.pretix-widget-availability-unavailable(v-else-if="unavailabilityReasonMessage")
		small {{ unavailabilityReasonMessage }}
	.pretix-widget-availability-unavailable(v-else-if="avail[0] < 100 && avail[0] > 10") {{ STRINGS.reserved }}
	.pretix-widget-availability-gone(v-else-if="avail[0] <= 10") {{ STRINGS.sold_out }}
	.pretix-widget-waiting-list-link(v-if="waitingListShow && !unavailabilityReasonMessage")
		a(:href="waitingListUrl", target="_blank", @click="$root.open_link_in_frame") {{ STRINGS.waiting_list }}
	.pretix-widget-availability-available(v-if="!unavailabilityReasonMessage && avail[0] === 100")
		label.pretix-widget-item-count-single-label.pretix-widget-btn-checkbox(v-if="orderMax === 1")
			input(
				ref="quantity",
				type="checkbox",
				value="1",
				:name="inputName",
				:aria-label="labelSelectItem"
			)
			span.pretix-widget-icon-cart(aria-hidden="true")
			|  {{ STRINGS.select }}

		.pretix-widget-item-count-group(v-else, role="group", :aria-label="item.name")
			button.pretix-widget-btn-default.pretix-widget-item-count-dec(
				type="button",
				data-step="-1",
				:data-controls="`input_${inputName}`",
				:aria-label="decLabel",
				@click.prevent.stop="onStep"
			)
				span -
			input.pretix-widget-item-count-multiple(
				:id="`input_${inputName}`",
				ref="quantity",
				type="number",
				inputmode="numeric",
				pattern="\\d*",
				placeholder="0",
				min="0",
				:max="orderMax",
				:name="inputName",
				:aria-labelledby="ariaLabelledby"
			)
			button.pretix-widget-btn-default.pretix-widget-item-count-inc(
				type="button",
				data-step="1",
				:data-controls="`input_${inputName}`",
				:aria-label="incLabel",
				@click.prevent.stop="onStep"
			)
				span +
</template>
<style lang="sass">
</style>
