<script lang="ts">
import QuestionnaireElement from './QuestionnaireElement.vue';
import * as api from './api';
import { Questionnaire } from './model';
import { i18n_any, QUESTION_TYPE, sort, localeComp, numericComp, groupBy, _ } from './helper';
import {Ref, ref} from 'vue';
import { SlickList, SlickItem } from 'vue-slicksort';

const items_list = await api.getItems();
const categories_list = await api.getCategories();
const categories = Object.fromEntries(categories_list.map(cat => [cat.id, cat]));
categories['null'] = { position: -1, internal_name: _('Uncategorized') };
sort(items_list, numericComp(item => categories[item.category]?.position), numericComp(item => item.position));
console.log("items_list", items_list);
const grouped_items = [...groupBy(items_list, item => categories[item.category])];
console.log("grouped_items", grouped_items);

const all_questionnaires: (Omit<Questionnaire, 'id'> & { _new_id?: number, id?: number })[] = await api.getQuestionnaires();
const order_questionnaires = ref(all_questionnaires.filter(q => q.type.startsWith('O')));
const position_questionnaires = ref(all_questionnaires.filter(q => q.type.startsWith('P')));
const datafields = ref(await api.getDatafields());

function saveQuestionnaire(questionnaire) {
	if (questionnaire.id) {
		api.updateQuestionnaire(questionnaire.id, questionnaire);
	} else {
		api.createQuestionnaire(questionnaire);
	}
}

export default {
  components: {
    QuestionnaireElement, SlickList, SlickItem,
  },
  methods: {
    i18n_any,
    addPositionQuestionnaire() {
      position_questionnaires.value.push({
	      all_sales_channels: false, children: [], limit_sales_channels: [], position: 0,
				items: [], internal_name: "Unnamed questionnaire", type: "PS",
				_new_id: Date.now(),
			});
    },
    addOrderQuestionnaire() {
      order_questionnaires.value.push({
	      all_sales_channels: false, children: [], limit_sales_channels: [], position: 0,
				items: [], internal_name: "Unnamed questionnaire", type: "OS",
				_new_id: Date.now(),
			});
    },
		saveData() {
			for (const questionnaire of order_questionnaires.value) {
				saveQuestionnaire(questionnaire);
			}
			for (const questionnaire of position_questionnaires.value) {
				saveQuestionnaire(questionnaire);
			}
		},
  },
  data() {
    return {
    	order_questionnaires,
      position_questionnaires,
      datafields,
      items: items_list,
      selected_product: ref(""),
      grouped_items,
      categories,
    }
  }
}
</script>

<style>
.hidden-question { opacity: 0.3; }
.hidden-question label { text-decoration: line-through; }

.question-editor { margin-right: 180px; }
.question-edit-buttons { float:right; }
.question-edit-buttons div { position: absolute; margin-left: 10px; min-width: 100px; }
.question-edit-buttons button {  }
.form-group { margin-bottom: 30px }

.filter-row { background: #fffee6; border: 1px solid #ecead5; padding: 10px; }

.debuginfo { font-size: 70%; background: rgba(200, 200, 200, 0.5); }
.dependency-info { position: absolute;  }
.dependency-info > span {  }

.category-header { margin: 8px 0 -5px 0; font-weight: bold; color: #737373; }
</style>
<template>
	<p class="filter-row">
		Order questionnaires
	</p>
	<div class="question-editor">
		<SlickList axis="y" v-model:list="order_questionnaires" useDragHandle appendTo="#orderQuestionnaireListParent" id="orderQuestionnaireListParent">
			<SlickItem v-for="(questionnaire, index) in order_questionnaires" :key="questionnaire.id || questionnaire._new_id" :index="index">
        <QuestionnaireElement
          :questionnaire="questionnaire"
          :datafields="datafields"
          :grouped_items="null"
          :selected_product="null" />
			</SlickItem>
		</SlickList>
	</div>
  <p>
		<button class="btn btn-default" @click="addOrderQuestionnaire()"><i class="fa fa-plus"></i> Neuen Fragebogen erstellen</button>
		<button class="btn btn-default" @click="saveData()"><i class="fa fa-save"></i> Speichern</button>
  </p>

	<p class="filter-row">
		Questionnaires for product:
		<select v-model="selected_product">
			<option value="">(all)</option>
			<optgroup v-for="[category, items] in grouped_items" :label="category.internal_name || i18n_any(category.name)">
				<option v-for="item in items" :value="item.id">
					{{ item.internal_name || i18n_any(item.name) }}
				</option>
			</optgroup>
		</select>
	</p>
	<div class="question-editor">
		<SlickList axis="y" v-model:list="position_questionnaires" useDragHandle appendTo="#questionnaireListParent" id="questionnaireListParent">
			<SlickItem v-for="(questionnaire, index) in position_questionnaires" :key="questionnaire.id || questionnaire._new_id" :index="index">
        <QuestionnaireElement
          :questionnaire="questionnaire"
          :datafields="datafields"
          :grouped_items="grouped_items"
          :selected_product="selected_product" />
			</SlickItem>
		</SlickList>
	</div>
  <p>
		<button class="btn btn-default" @click="addPositionQuestionnaire()"><i class="fa fa-plus"></i> Neuen Fragebogen erstellen</button>
		<button class="btn btn-default" @click="saveData()"><i class="fa fa-save"></i> Speichern</button>
  </p>
</template>
