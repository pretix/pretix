<script setup>
import { i18n_any, QUESTION_TYPE, QUESTION_TYPE_LABEL, SYSTEM_DATAFIELDS } from './helper';
import NativeDialog from './NativeDialog.vue';
import I18nTextField from './I18nTextField.vue';
import { useId, ref } from 'vue'
const id = useId();
const props = defineProps(['question', 'datafields', 'editable'])
const emit = defineEmits(['removeSelf']);

const df = typeof props.question.question === 'number' ?
		props.datafields.find(el => el.id === props.question.question) :
	typeof props.question.question === 'string' ?
		SYSTEM_DATAFIELDS[props.question.question] :
		{};

if (!props.question.label) props.question.label = {};
if (!props.question.help_text) props.question.help_text = {};

const editor = ref();
</script>

<template>
  <div class="form-group">
    <div class="question-edit-buttons" v-if="editable"><div>
      <button class="btn btn-default"><i class="fa fa-arrows"></i></button>
      <button class="btn btn-default" @click="editor.show()"><i class="fa fa-edit"></i></button>
    </div></div>
    <label class="col-md-3 control-label" :for="id" v-if="df.type !== QUESTION_TYPE.BOOLEAN">
      {{ i18n_any(question.label) }}
    </label>
    <div v-else class="col-md-3 control-label label-empty"></div>
    <div class="col-md-9">
      <input :id="id" type="text" v-if="df.type === QUESTION_TYPE.STRING" class="form-control">
			<textarea :id="id" v-if="df.type === QUESTION_TYPE.TEXT" class="form-control"></textarea>
      <div class="checkbox" v-if="df.type === QUESTION_TYPE.BOOLEAN">
        <label :for="id">
          <input :id="id" type="checkbox"> {{ i18n_any(question.label) }}
        </label>
      </div>
      <input :id="id" type="number" v-if="df.type === QUESTION_TYPE.NUMBER" class="form-control">
      <input :id="id" type="file" v-if="df.type === QUESTION_TYPE.FILE" class="form-control">
      <select :id="id"
        v-if="df.type === QUESTION_TYPE.CHOICE || df.type === QUESTION_TYPE.CHOICE_MULTIPLE"
        :multiple="df.type === QUESTION_TYPE.CHOICE_MULTIPLE" class="form-control">
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
            <I18nTextField :value="question.label"/>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            Data field type
          </label>
          <div class="col-md-9">
            <select v-model="df.type" class="form-control">
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
        <button @click="editor.close()" class="btn btn-primary pull-right"><span class="fa fa-check"></span> Save and close</button>
        <button @click="emit('removeSelf')" class="btn btn-default">Remove from questionnaire</button>
    </NativeDialog>
  </Teleport>
</template>
