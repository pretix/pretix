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
		form(ref="form", :method="formMethod", :action="store.formAction", :target="store.formTarget")
			input(v-if="store.voucherCode", type="hidden", name="_voucher_code", :value="store.voucherCode")
			input(v-if="store.voucherCode", type="hidden", name="voucher", :value="store.voucherCode")
			input(type="hidden", name="subevent", :value="store.subevent")
			input(type="hidden", name="locale", :value="lang")
			input(type="hidden", name="widget_data", :value="store.widgetDataJson")
			input(v-if="store.consentParameterValue", type="hidden", name="consent", :value="store.consentParameterValue")
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
