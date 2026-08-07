<script setup lang="ts">
import { i18n_any, QUESTION_TYPE, QUESTION_TYPE_LABEL, SYSTEM_DATAFIELDS } from './helper';
import NativeDialog from './NativeDialog.vue';
import I18nTextField from './I18nTextField.vue';
import {useId, ref, computed} from 'vue'
import { DragHandle } from 'vue-slicksort';
import {getDatafieldEditUrl} from "./api";

const id = useId();
const props = defineProps(['question', 'datafields', 'editable', 'possible_dependencies'])
const emit = defineEmits(['removeSelf']);
const gettext = (window as any).gettext;
const question = ref(props.question);

const df = typeof question.value.question === 'number' ?
		props.datafields.find(el => el.id === question.value.question) :
	typeof question.value.question === 'string' ?
		SYSTEM_DATAFIELDS[question.value.question] :
		null;

const dependency_values_options = computed(() => props.datafields.find(el => el.id === question.value.dependency_question)?.options);
const dependency_values_resolved = computed(() => question.value.dependency_values.map(ident => i18n_any(dependency_values_options.value.find(opt => opt.identifier === ident)?.answer) ?? ident));

if (!question.value.label) question.value.label = {};
if (!question.value.help_text) question.value.help_text = {};

const editor = ref();
</script>

<template>
  <div class="form-group">
    <div class="question-edit-buttons" v-if="editable"><div class="btn-group">
			<DragHandle tag="button" class="btn btn-default"><i class="fa fa-arrows"></i></DragHandle>
      <button class="btn btn-default" @click="editor.show()"><i class="fa fa-edit"></i></button>
    </div></div>

		<template v-if="df">
			<div v-if="question.dependency_question" class="dependency-info debuginfo">
				<span><span class="fa fa-link"></span> {{ question.dependency_question }} = {{ dependency_values_resolved }}</span>
			</div>
			<div class="col-md-3 control-label label-empty" v-if="df.type === QUESTION_TYPE.BOOLEAN"></div>
			<label class="col-md-3 control-label" :for="id" v-else>
				{{ i18n_any(question.label) }}
			</label>
			<div class="col-md-9">
				<input :id="id" type="text" v-if="df.type === QUESTION_TYPE.STRING || df.type === QUESTION_TYPE.PHONENUMBER" class="form-control">
				<textarea :id="id" v-if="df.type === QUESTION_TYPE.TEXT" class="form-control"></textarea>
				<div class="checkbox" v-if="df.type === QUESTION_TYPE.BOOLEAN">
					<label :for="id">
						<input :id="id" type="checkbox"> {{ i18n_any(question.label) }}
					</label>
				</div>
				<input :id="id" type="number" v-if="df.type === QUESTION_TYPE.NUMBER" class="form-control">
				<input :id="id" type="file" v-if="df.type === QUESTION_TYPE.FILE" class="form-control">
				<select :id="id" class="form-control"
					v-if="df.type === QUESTION_TYPE.CHOICE || df.type === QUESTION_TYPE.COUNTRYCODE">
					<option></option>
					<option v-for="opt in df.options">{{ i18n_any(opt.answer) }}</option>
				</select>
				<div class="checkbox" v-if="df.type === QUESTION_TYPE.CHOICE_MULTIPLE" v-for="(opt, index) in df.options">
					<label :for="`${id}-${index}`">
						<input :id="`${id}-${index}`" type="checkbox"> {{ i18n_any(opt.answer) }}
					</label>
				</div>
				<div class="help-block">{{ i18n_any(question.help_text) }}</div>
			</div>
		</template>
		<div v-else class="col-md-12">
			<h3>{{ i18n_any(question.label) }}</h3>
			<p>{{ i18n_any(question.help_text) }}</p>
		</div>
  </div>

  <Teleport to="body">
    <NativeDialog ref="editor" class="modal-card"
                  title="Edit question">
        <div class="form-group">
          <label class="col-md-3 control-label">
            {{ gettext('Question') }}
          </label>
          <div class="col-md-9">
            <I18nTextField :value="question.label"/>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            {{ gettext('Help text') }}
          </label>
          <div class="col-md-9">
            <I18nTextField :value="question.help_text"/>
            <div class="help-block">Wenn diese Frage noch weitere Erklärung braucht, können Sie sie hier eintragen.</div>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            Data field
          </label>
          <div class="col-md-9">
            <p class="form-control-static">
							<template v-if="typeof question.question === 'number'">
								{{ df.internal_name }}
								<a :href="getDatafieldEditUrl(df.id)" target="_blank">Manage data field details</a>
							</template>
							<template v-else>
								{{ question.question }}
							</template>
						</p>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            Data field type
          </label>
          <div class="col-md-9">
            <select v-model="df.type" class="form-control" disabled>
              <option v-for="(label, type) in QUESTION_TYPE_LABEL" :value="QUESTION_TYPE[type]">{{ label }}</option>
            </select>
          </div>
        </div>
        <div class="form-group">
        	<label class="col-md-3 control-label label-empty">&nbsp;</label>
          <div class="col-md-9">
          	<div class="checkbox">
							<label>
								<input type="checkbox" v-model="question.required">
								{{ gettext('Required question') }}
							</label>
						</div>
          </div>
        </div>

        <div class="form-group">
          <label class="col-md-3 control-label">
            {{ gettext('Only visible if...') }}
          </label>
          <div class="col-md-9">
            <select v-model="question.dependency_question" class="form-control">
              <option :value="null">{{ gettext('(none)') }}</option>
              <option v-for="(qc, index) in possible_dependencies" :value="qc.question">{{ i18n_any(qc.label) }}</option>
            </select>
            <select v-model="question.dependency_values" class="form-control" multiple>
              <option v-for="(qc, index) in dependency_values_options" :value="qc.identifier">{{ i18n_any(qc.answer) }}</option>
            </select>
						<div v-if="question.dependency_question">
							<p><span class="debuginfo">depends on {{ question.dependency_question }} = {{ dependency_values_resolved }}</span></p>
						</div>
          </div>
        </div>

        <button @click="editor.close()" class="btn btn-primary pull-right"><span class="fa fa-check"></span> Save and close</button>
        <button @click="emit('removeSelf')" class="btn btn-default">Remove from questionnaire</button>
    </NativeDialog>
  </Teleport>
</template>
