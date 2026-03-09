<script setup lang="ts">
import type { Category } from '~/types'
import Item from './Item.vue'

defineProps<{
	category: Category
}>()
</script>

<template lang="pug">
.pretix-widget-category(:data-id="category.id")
	h3.pretix-widget-category-name(v-if="category.name") {{ category.name }}
	.pretix-widget-category-description(v-if="category.description", v-html="category.description")
	.pretix-widget-category-items
		Item(
			v-for="item in category.items",
			:key="item.id",
			:item="item",
			:category="category"
		)
</template>
<style lang="sass">
</style>
