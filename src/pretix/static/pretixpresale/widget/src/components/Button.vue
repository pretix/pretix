<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { StoreKey } from '~/sharedStore'
import Overlay from './Overlay.vue'

const lang = LANG // we need this so the template sees the variable

const store = inject(StoreKey)!

const form = ref<HTMLFormElement>()

const formMethod = computed(() => {
	if (!store.useIframe && store.isButton && store.items.length === 0) {
		return 'get'
	}
	return 'post'
})

const formAction = computed(() => store.getFormAction())

const formTarget = computed(() => {
	const isFirefox = navigator.userAgent.toLowerCase().includes('firefox')
	const isAndroid = navigator.userAgent.toLowerCase().includes('android')
	if (isAndroid && isFirefox) {
		return '_top'
	}
	return '_blank'
})

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

function handleBuy (event: Event) {
	if (form.value) {
		const formData = new FormData(form.value)
		store.buy(formData, event)
	}
}

defineExpose({
	form,
	buy: handleBuy,
})
</script>
<template lang="pug">
.pretix-widget-wrapper
	.pretix-widget-button-container
		form(ref="form", :method="formMethod", :action="formAction", :target="formTarget")
			input(v-if="store.voucherCode", type="hidden", name="_voucher_code", :value="store.voucherCode")
			input(v-if="store.voucherCode", type="hidden", name="voucher", :value="store.voucherCode")
			input(type="hidden", name="subevent", :value="store.subevent")
			input(type="hidden", name="locale", :value="lang")
			input(type="hidden", name="widget_data", :value="widgetDataJson")
			input(v-if="consentParameterValue", type="hidden", name="consent", :value="consentParameterValue")
			input(
				v-for="item in store.items",
				:key="item.item",
				type="hidden",
				:name="item.item",
				:value="item.count"
			)
			button.pretix-button(@click="handleBuy", v-html="store.buttonText")
		.pretix-widget-clear

	Overlay
</template>

<style lang="sass">
</style>
