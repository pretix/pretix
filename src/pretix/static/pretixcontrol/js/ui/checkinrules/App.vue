<script setup lang="ts">
import { computed } from 'vue'
import { rules as rawRules, items, allProducts, limitProducts } from './django-interop'
import { convertToDNF } from './jsonlogic-boolalg'

import RulesEditor from './checkin-rules-editor.vue'
import RulesVisualization from './checkin-rules-visualization.vue'

const gettext = (window as any).gettext

const missingItems = computed(() => {
	// This computed variable contains list of item or variation names that
	// a) Are allowed on the checkin list according to all_products or include_products
	// b) Are not matched by ANY logical branch of the rule.
	// The list will be empty if there is a "catch-all" rule.
	let productsSeen = {}
	let variationsSeen = {}
	let rules = convertToDNF(rawRules.value)
	let branchWithoutProductFilter = false

	if (!rules.or) {
		rules = { or: [rules] }
	}

	for (let part of rules.or) {
		if (!part.and) {
			part = { and: [part] }
		}
		let thisBranchWithoutProductFilter = true
		for (let subpart of part.and) {
			if (subpart.inList) {
				if (subpart.inList[0].var === 'product' && subpart.inList[1]) {
					thisBranchWithoutProductFilter = false
					for (let listentry of subpart.inList[1].objectList) {
						productsSeen[parseInt(listentry.lookup[1])] = true
					}
				} else if (subpart.inList[0].var === 'variation' && subpart.inList[1]) {
					thisBranchWithoutProductFilter = false
					for (let listentry_ of subpart.inList[1].objectList) {
						variationsSeen[parseInt(listentry_.lookup[1])] = true
					}
				}
			}
		}
		if (thisBranchWithoutProductFilter) {
			branchWithoutProductFilter = true
			break
		}
	}
	if (branchWithoutProductFilter || (!Object.keys(productsSeen).length && !Object.keys(variationsSeen).length)) {
		// At least one branch with no product filters at all – that's fine.
		return []
	}

	let missing = []
	for (const item of items.value) {
		if (productsSeen[item.id]) continue
		if (!allProducts.value && !limitProducts.value.includes(item.id)) continue
		if (item.variations.length > 0) {
			for (let variation of item.variations) {
				if (variationsSeen[variation.id]) continue
				missing.push(item.name + ' – ' + variation.name)
			}
		} else {
			missing.push(item.name)
		}
	}
	return missing
})
</script>
<template lang="pug">
#rules-editor.form-inline
	div
		ul.nav.nav-tabs(role="tablist")
			li.active(role="presentation")
				a(href="#rules-edit", role="tab", data-toggle="tab")
					span.fa.fa-edit
					| {{ gettext("Edit") }}
			li(role="presentation")
				a(href="#rules-viz", role="tab", data-toggle="tab")
					span.fa.fa-eye
					| {{ gettext("Visualize") }}

		//- Tab panes
		.tab-content
			#rules-edit.tab-pane.active(v-if="items", role="tabpanel")
				RulesEditor
			#rules-viz.tab-pane(role="tabpanel")
				RulesVisualization

	.alert.alert-info(v-if="missingItems.length")
		p {{ gettext("Your rule always filters by product or variation, but the following products or variations are not contained in any of your rule parts so people with these tickets will not get in:") }}
		ul
			li(v-for="h in missingItems", :key="h") {{ h }}
		p {{ gettext("Please double-check if this was intentional.") }}
</template>
<style lang="stylus">
</style>
