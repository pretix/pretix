<script>
import Questionnaire from './Questionnaire.vue';
import {get_datafields, get_items, get_questionnaires} from './api';
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
    Questionnaire
  },
  methods: {
    i18n_any,
    addQuestionnaire: function() {
      questionnaires.value.push({
        items: [], internal_name: "Unnamed questionnaire",
        type: 'PS',
      });
    }
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
</style>
<template>

	<p>
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
			<SlickItem v-for="(questionnaire, index) in questionnaires" :key="questionnaire.id" :index="index">
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
  </p>
</template>
