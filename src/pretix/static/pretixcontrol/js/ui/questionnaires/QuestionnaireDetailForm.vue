<script setup lang="ts">
import {gettext} from "./gettextstub";
import {GroupedItems, Questionnaire, SalesChannel} from "./model";
import {inject, Ref, useId} from "vue";
import {i18n_any, QUESTIONNAIRE_TYPE, QUESTIONNAIRE_TYPE_LABEL, setListState} from "./helper";
import SalesChannelIcon from "./SalesChannelIcon.vue";

const sales_channels: Ref<SalesChannel[]> = inject('pretix:env:organizer:sales_channels')

const id = useId()

const props = defineProps<{
	questionnaire: Questionnaire,
	grouped_items: GroupedItems,
}>()

</script>

<template>
	<div class="form-group">
		<label class="col-md-3 control-label">
			{{ gettext('Internal name') }}
		</label>
		<div class="col-md-9">
			<input type="text" class="form-control" v-model="questionnaire.internal_name"/>
		</div>
	</div>
	<div class="form-group">
		<label class="col-md-3 control-label">
			{{ gettext('When to ask') }}
		</label>
		<div class="col-md-9">
			<select v-model="questionnaire.type" class="form-control">
        <template v-for="(label, type) in QUESTIONNAIRE_TYPE_LABEL">
				  <option v-if="QUESTIONNAIRE_TYPE[type][0] == questionnaire.type[0]" :value="QUESTIONNAIRE_TYPE[type]">{{ label }}</option>
        </template>
			</select>
		</div>
	</div>
	<div class="form-group" v-if="questionnaire.type[1] == 'S'">
		<label class="col-md-3 control-label">
			{{ gettext('Sales channels') }}
		</label>
		<div class="col-md-9">
			<div class="checkbox">
				<label>
					<input type="checkbox" v-model="questionnaire.all_sales_channels"> {{ gettext('All sales channels') }}
				</label>
			</div>
			<div class="checkbox" v-for="channel in sales_channels">
				<label>
					<input type="checkbox" :checked="questionnaire.all_sales_channels || questionnaire.limit_sales_channels.indexOf(channel.identifier) !== -1"
								 @change="e => setListState(questionnaire.limit_sales_channels, (e.target as HTMLInputElement).checked, channel.identifier)"
								 :disabled="questionnaire.all_sales_channels">
          <SalesChannelIcon :sales-channel="channel"/>
					{{ i18n_any(channel.label) }}
				</label>
			</div>
		</div>
	</div>
	<div class="form-group" v-if="grouped_items">
		<label class="col-md-3 control-label">
			{{ gettext('Visible on products') }}
		</label>
		<div class="col-md-9">
			<div v-for="[category, items] in grouped_items">
				<div class="category-header">{{ category.internal_name || i18n_any(category.name) }}</div>
				<div class="checkbox" v-for="item in items">
					<label :for="id + '_' + item.id">
						<input :id="id + '_' + item.id" type="checkbox" :checked="questionnaire.items.indexOf(item.id) !== -1" @change="e => setListState(questionnaire.items, (e.target as HTMLInputElement).checked, item.id)"> {{ item.internal_name || i18n_any(item.name) }}
					</label>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped lang="sass">

</style>
