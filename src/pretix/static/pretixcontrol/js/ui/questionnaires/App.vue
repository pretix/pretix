<script lang="ts">
import QuestionnaireElement from './QuestionnaireElement.vue';
import {create_questionnaire, get_datafields, get_items, get_questionnaires, update_questionnaire} from './api';
import { Questionnaire } from './model';
import { i18n_any, QUESTION_TYPE } from './helper';
import {Ref, ref} from 'vue';
import { SlickList, SlickItem } from 'vue-slicksort';

const items_list = await get_items();

const questionnaires: Ref<(Omit<Questionnaire, 'id'> & { _new_id?: number, id?: number })[]> = ref(await get_questionnaires());
const datafields = ref(await get_datafields());

export default {
  components: {
    QuestionnaireElement, SlickList, SlickItem,
  },
  methods: {
    i18n_any,
    addQuestionnaire() {
      questionnaires.value.push({
	      all_sales_channels: false, children: [], limit_sales_channels: [], position: 0,
				items: [], internal_name: "Unnamed questionnaire", type: "PC",
				_new_id: Date.now(),
			});
    },
		saveData() {
			console.log(JSON.parse(JSON.stringify(questionnaires.value)));
			for (const questionnaire of questionnaires.value) {
				if (questionnaire.id) {
					update_questionnaire(questionnaire.id, questionnaire);
				} else {
					create_questionnaire(questionnaire);
				}
			}
		},
  },
  data() {
    return {
      questionnaires,
      datafields,
      items: items_list,
      selected_product: ref(""),
    }
  }
}
</script>

<style>
.hidden-question { opacity: 0.3; }
.hidden-question label { text-decoration: line-through; }

.question-editor { margin-right: 140px; }
.question-edit-buttons { float:right }
.question-edit-buttons div { position: absolute; margin-left: 10px; }
.question-edit-buttons button {  }
.form-group { margin-bottom: 30px }

.filter-row { background: #fffee6; border: 1px solid #ecead5; padding: 10px; }
</style>
<template>
	<p class="filter-row">
		Questionnaires for product:
		<select v-model="selected_product">
			<option value="">(all)</option>
			<option v-for="item in items" :value="item.id">
				{{ i18n_any(item.name) }}
			</option>
		</select>
	</p>
	<div class="question-editor">
		<SlickList axis="y" v-model:list="questionnaires" useDragHandle appendTo="#questionnaireListParent" id="questionnaireListParent">
			<SlickItem v-for="(questionnaire, index) in questionnaires" :key="questionnaire.id || questionnaire._new_id" :index="index">
        <QuestionnaireElement
          :questionnaire="questionnaire"
          :datafields="datafields"
          :items="items"
          :selected_product="selected_product" />
			</SlickItem>
		</SlickList>
	</div>
  <p>
		<button class="btn btn-default" @click="addQuestionnaire()"><i class="fa fa-plus"></i> Neuen Fragebogen erstellen</button>
		<button class="btn btn-default" @click="saveData()"><i class="fa fa-save"></i> Speichern</button>
  </p>
</template>
