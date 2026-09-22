<script setup lang="ts">
import {useId, ref, computed, onMounted, watch} from 'vue'
import QuestionElement from "./QuestionElement.vue";
import {
	i18n_any,
	QUESTION_TYPE,
	QUESTION_TYPE_LABEL,
	QUESTIONNAIRE_TYPE,
	QUESTIONNAIRE_TYPE_LABEL, setListState,
	SYSTEM_DATAFIELDS
} from "./helper";
import { gettext } from './gettextstub';
import I18nTextField from "./I18nTextField.vue";
import NativeDialog from "./NativeDialog.vue";
import { SlickList, SlickItem, DragHandle } from 'vue-slicksort';
import {getDatafieldCreateUrl} from "./api";
import DjangoDialog from "./DjangoDialog.vue";
import * as api from './api';
import QuestionnaireDetailForm from "./QuestionnaireDetailForm.vue";

const dlgEditor = ref()
const dlgAddExisting = ref()
const dlgAddTextblock = ref()
const dlgNewDatafield = ref()

const newTextblockTitle = ref()
const newTextblockText = ref()

const id = useId();
const props = defineProps(['questionnaire', 'datafields', 'selected_product', 'grouped_items', 'preview_mode', 'err_mes'])
const emit = defineEmits(['update', 'invalidate:datafields', 'invalidate:questionnaires'])

let nextId = 1;
watch(() => props.questionnaire.children, () => {
	for (let qc of props.questionnaire.children) {
		if (!qc._cid) qc._cid = id + (++nextId);
	}
})

function addExistingDatafield (field) {
	props.questionnaire.children.push({
		_cid: useId(),
		question: field.id,
		required: false,
		label: field.question,
		help_text: {},
		dependency_question: null,
		dependency_values: [],
	})
	dlgAddExisting.value.close()
	emit('update')
}

function showAddTextblockDialog () {
	newTextblockTitle.value = {}
	newTextblockText.value = {}
	dlgAddTextblock.value.show()
}

function addTextblock () {
	props.questionnaire.children.push({
		_cid: useId(),
		question: null,
		required: false,
		label: newTextblockTitle.value,
		help_text: newTextblockText.value,
		dependency_question: null,
		dependency_values: [],
	})
	dlgAddTextblock.value.close()
	emit('update')
}

function newDatafield (container_type) {
	dlgNewDatafield.value.open(getDatafieldCreateUrl(props.questionnaire.type[0]))
}

async function onNewDatafieldCreated (data) {
	watch(
		() => props.datafields,
		(newValue, oldValue) => {
			console.log('datafields changed watcher called')
			addExistingDatafield(newValue.find(f => f.id === data.object))
		},
		{ once: true }
	)
	emit('invalidate:datafields')
}

async function deleteQuestionnaire () {
	if (confirm("Are you sure?")) {
		try {
			await api.deleteQuestionnaire(props.questionnaire.id)
		} catch (e) {
			console.error('Failed to delete questionnaire', e)
			alert('Error while deleting questionnaire')
		}
		emit('invalidate:questionnaires')
	}
}

const isHidden = computed(() => props.selected_product && props.questionnaire.items.indexOf(props.selected_product) === -1)
const isEditable = computed(() => props.selected_product && props.questionnaire.items.indexOf(props.selected_product) !== -1)

</script>


<template>

  <details class="questionnaire-panel" :open="preview_mode"
    :class="{ 'hidden-questionnaire': isHidden }">
    <summary class="questionnaire-panel-heading">
			<div class=" editor-row">
				<div class="editor-preview-area">
					<input type="checkbox" @change="e => {setListState(props.questionnaire.items, selected_product, e.target.checked); emit('update')}" v-if="selected_product && !preview_mode" :checked="!isHidden">
					{{ props.questionnaire.internal_name }}
					<span class="fa fa-warning" v-if="questionnaire._err_mes"></span>
					<span class="fa fa-cog fa-spin" v-if="questionnaire._loading"></span>
				</div>

				<aside class="editor-action-area"><div class="btn-group">
					<DragHandle tag="button" class="btn btn-default" v-if="!preview_mode"><i class="fa fa-arrows"></i></DragHandle>
					<button class="btn btn-default" @click="dlgEditor.show()"><i class="fa fa-wrench"></i></button>
				</div></aside>
			</div>
    </summary>
    <div class="questionnaire-panel-body" v-if="!isHidden">
			<div class="alert alert-warning" v-if="questionnaire._err_mes">{{ questionnaire._err_mes }}</div>
      <div class="form-horizontal" :id="`questionListParent${props.questionnaire.id}`">
				<SlickList axis="y" v-model:list="props.questionnaire.children" useDragHandle :appendTo="`#questionListParent${props.questionnaire.id}`" @update:list="emit('update')">
					<SlickItem v-for="(child, index) in props.questionnaire.children" :key="child._cid" :index="index">
						<QuestionElement
										:datafields="props.datafields"
										:question="child"
										:editable="true"
										:possible_dependencies="props.questionnaire.children.slice(0, index)"
										@remove-self="questionnaire.children.splice(index, 1); emit('update')"
										@update="emit('update')"
										@invalidate:datafields="emit('invalidate:datafields')"/>
					</SlickItem>
				</SlickList>
      </div>
			<div class="editor-action-row form-horizontal">
				<div class="form-group">
					<div class="col-md-9 col-md-push-3">
						<p class="btn-group" role="group">
								<button class="btn btn-default" @click="dlgAddExisting.show()"><i class="fa fa-plus"></i> {{ gettext('Existing data field') }}</button>
								<button class="btn btn-default" @click="newDatafield(questionnaire.type[0])"><i class="fa fa-plus"></i> {{ gettext('New data field') }}</button>
								<button class="btn btn-default" @click="showAddTextblockDialog()"><i class="fa fa-plus"></i> {{ gettext('Text') }}</button>
						</p>
					</div>
				</div>
			</div>
    </div>
  </details>

  <Teleport to="body">
    <NativeDialog ref="dlgEditor" class="modal-card"
                  :title="gettext('Edit questionnaire')">
			<QuestionnaireDetailForm :questionnaire="questionnaire" :grouped_items="grouped_items"/>

			<button @click="dlgEditor.close(); emit('update')" class="btn btn-primary pull-right"><span class="fa fa-check"></span> {{ gettext('Save and close') }}</button>
			<button @click="deleteQuestionnaire" class="btn btn-default">{{ gettext('Delete') }}</button>
    </NativeDialog>

    <NativeDialog ref="dlgAddExisting" class="modal-card"
                  :title="gettext('Add existing data field')">

				<div class="list-group">
					<a href="javascript:" @click="addExistingDatafield(field)" v-for="field in datafields" class="list-group-item">{{ i18n_any(field.question) }}</a>
				</div>

        <button @click="dlgAddExisting.close()" class="btn btn-default pull-right">{{ gettext('Cancel') }}</button>
    </NativeDialog>

    <NativeDialog ref="dlgAddTextblock" class="modal-card"
                  :title="gettext('Add sub heading')">

        <div class="form-group">
          <label class="col-md-3 control-label">
            {{ gettext('Title') }}
          </label>
          <div class="col-md-9">
            <I18nTextField :value="newTextblockTitle"/>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            {{ gettext('Text') }}
          </label>
          <div class="col-md-9">
            <I18nTextField :value="newTextblockText"/>
          </div>
        </div>

        <button @click="addTextblock()" class="btn btn-default pull-right">{{ gettext('OK') }}</button>
        <button @click="dlgAddTextblock.close()" class="btn btn-default pull-right">{{ gettext('Cancel') }}</button>

    </NativeDialog>

		<DjangoDialog ref="dlgNewDatafield" @confirm="onNewDatafieldCreated" max-width="60em"></DjangoDialog>
  </Teleport>
</template>
