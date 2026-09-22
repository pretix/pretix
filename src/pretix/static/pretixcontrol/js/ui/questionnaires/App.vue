<script setup lang="ts">
import Editor from './Editor.vue';
import {provide, ref} from "vue";
import * as api from "./api";
import {sort, numericComp, groupBy} from './helper';
import {Category, GroupedItems, Item, SalesChannel} from "./model";

const sales_channels_list = ref<SalesChannel[]>();
const grouped_items = ref<GroupedItems>()

provide('pretix:env:organizer:sales_channels', sales_channels_list)
provide('pretix:env:event:grouped_items', grouped_items)

async function loadEnvironmentData() {
	sales_channels_list.value = await api.getSalesChannels();
	const items_list = await api.getItems();
	const categories_list = await api.getCategories();
	const categories = Object.fromEntries(categories_list.map(cat => [cat.id, cat]));
	categories['null'] = { position: -1, internal_name: gettext('Uncategorized'), name: null, id: null };
	sort(items_list, numericComp(item => categories[item.category]?.position), numericComp(item => item.position));
	grouped_items.value = [...groupBy(items_list, item => categories[item.category])]
}
loadEnvironmentData()

</script>

<template>
	<Suspense>
		<Editor/>

		<template #fallback>
			<div class="big-load-indicator"><i class="fa fa-cog big-rotating-icon"></i></div>
		</template>
	</Suspense>
</template>
<style>
.big-load-indicator { text-align: center; padding-bottom: 100px }

.progressBar { position: fixed; top: 0; left: 0; right: 0; z-index:1000000; pointer-events: none; }
.progressBar.local { position: absolute;  }
.progressBar .progressBar_progress { height: 5px; background: #0091EA; border-bottom: #026099; }
.progressBar .progressBar_progress.indeterminate {
    width: 30%; animation: slide 5s forwards;
}
.progressBarText { width: 100%; color: white; text-shadow: 1px 1px 1px black, -1px -1px 1px black;
    font-weight: bold; padding-left: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;  }
@keyframes slide {
    0% { width: 20%; }
    30% { width: 50%; }
    100% { width: 60%; }
}
</style>
