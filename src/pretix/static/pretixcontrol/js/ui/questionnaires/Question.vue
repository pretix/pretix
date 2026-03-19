<script setup>
import { i18n_any, QUESTION_TYPE, QUESTION_TYPE_LABEL } from './helper';
import NativeDialog from './NativeDialog.vue';
import I18nTextField from './I18nTextField.vue';
import { useId, ref } from 'vue'
const id = useId();
const props = defineProps(['question', 'selected_product'])

function toggleItem() {
  const i = props.question.items.indexOf(props.selected_product);
  if (i === -1) {
    props.question.items.push(props.selected_product);
  } else {
    props.question.items.splice(i, 1);
  }
}
const editor = ref();
</script>

<template>
  <div class="form-group"
    :class="{ 'hidden-question': selected_product && question.items.indexOf(selected_product) === -1 }">
    <div class="question-edit-buttons"><div>
      <button class="btn btn-default"><i class="fa fa-arrows"></i></button>
      <button class="btn btn-default" @click="editor.show()"><i class="fa fa-edit"></i></button>
      <button class="btn btn-default" @click="toggleItem()" v-if="selected_product"><i :class="`fa fa-eye${(question.items.indexOf(selected_product) === -1) ? '-slash':''}`"></i></button>
    </div></div>
    <label class="col-md-3 control-label" :for="id" v-if="question.type != QUESTION_TYPE.BOOLEAN">
      {{ i18n_any(question.question) }}
    </label>
    <div v-else class="col-md-3 control-label label-empty"></div>
    <div class="col-md-9">

      <input :id="id" type="text" v-if="question.type == QUESTION_TYPE.TEXT" class="form-control">
      <div class="checkbox" v-if="question.type == QUESTION_TYPE.BOOLEAN">
        <label :for="id">
          <input :id="id" type="checkbox"> {{ i18n_any(question.question) }}
        </label>
      </div>
      <input :id="id" type="number" v-if="question.type == QUESTION_TYPE.NUMBER" class="form-control">
      <input :id="id" type="file" v-if="question.type == QUESTION_TYPE.FILE" class="form-control">
      <select :id="id"
        v-if="question.type == QUESTION_TYPE.CHOICE || question.type == QUESTION_TYPE.CHOICE_MULTIPLE"
        :multiple="question.type == QUESTION_TYPE.CHOICE_MULTIPLE" class="form-control">
        <option></option>
        <option v-for="opt in question.options">{{ i18n_any(opt.answer) }}</option>
      </select>
      <div class="help-block">{{ i18n_any(question.help_text) }}</div>
    </div>

  </div>

  <Teleport to="body">
    <NativeDialog ref="editor" class="modal-card"
                  title="Edit question">
        <div class="form-group">
          <label class="col-md-3 control-label">
            Question
          </label>
          <div class="col-md-9">
            <I18nTextField :value="question.question"/>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            Question type
          </label>
          <div class="col-md-9">
            <select v-model="question.type" class="form-control">
              <option v-for="(label, type) in QUESTION_TYPE_LABEL" :value="QUESTION_TYPE[type]">{{ label }}</option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            Help text
          </label>
          <div class="col-md-9">
            <I18nTextField :value="question.help_text"/>
            <div class="help-block">Wenn diese Frage noch weitere Erklärung braucht, können Sie sie hier eintragen.</div>
          </div>
        </div>
        <button @click="editor.close()">Close</button>
    </NativeDialog>
  </Teleport>
</template>
