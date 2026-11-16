<script setup lang="ts">
import type { PreviewProps } from '@/pretix/static/pretixcontrol/wallet/preview.d.ts'

import Google from './google.vue'
import FieldGroupEntries from './FieldGroupEntries.vue'

const props = defineProps<PreviewProps>()

</script>

<template lang="pug">
	Google(v-bind="props")
		template(#card-rows)
			FieldGroupEntries.card-row(fieldgroup="second_row" :fieldgroupContents="fieldgroupContents")
			FieldGroupEntries.card-row(fieldgroup="third_row" :fieldgroupContents="fieldgroupContents")

		template(#details)
			FieldGroupEntries.f-column(fieldgroup="details" :fieldgroupContents="fieldgroupContents")

</template>
