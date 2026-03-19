<script>
import Question from './Question.vue';
import {get_questions, get_items} from './api';
import { i18n_any, QUESTION_TYPE } from './helper';
import { ref } from 'vue';

const questions_response = await get_questions();
const items_response = await get_items();

const questions = ref(questions_response.results);
export default {
  components: {
    Question
  },
  methods: {
    i18n_any,
    addQuestion: function() {
      questions.value.push({
        items: [], question: {en:"Untitled question"},
        type: QUESTION_TYPE.TEXT, help_text: {en:"Help text"},
      })
      console.log(questions.value)
    }
  },
  data() {
    return {
      questions,
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
      <button class="btn btn-default" @click="addQuestion()"><i class="fa fa-plus"></i> Neue Frage erstellen</button>
  </p>

  <div class="panel panel-default question-editor">
    <div class="panel-heading">
      Edit questions for product:
      <select v-model="selected_product">
        <option value="">(all)</option>
        <option v-for="item in items" :value="item.id">
          {{ i18n_any(item.name) }}
        </option>
      </select>
    </div>
    <div class="panel-body">
      <div class="form-horizontal">

        <Question
          v-for="question in questions"
          :question="question"
          :selected_product="selected_product" />

      </div>
    </div>
  </div>


</template>
