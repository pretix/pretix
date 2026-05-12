<script>
import Questionnaire from './Questionnaire.vue';
import {create_questionnaire, get_datafields, get_items, get_questionnaires, update_questionnaire} from './api';
import { i18n_any, QUESTION_TYPE } from './helper';
import { ref } from 'vue';
import { SlickList, SlickItem } from 'vue-slicksort';

const datafields_response = await get_datafields();
const questionnaires_response = await get_questionnaires();
const items_response = await get_items();

const questionnaires = ref(questionnaires_response.results);
const datafields = ref(datafields_response.results);

export default {
  components: {
    Questionnaire, SlickList, SlickItem
  },
  methods: {
    i18n_any,
    addQuestionnaire() {
      questionnaires.value.push({
        items: [], internal_name: "Unnamed questionnaire",
        type: 'PS',
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
      items: items_response.results,
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
        <Questionnaire
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
