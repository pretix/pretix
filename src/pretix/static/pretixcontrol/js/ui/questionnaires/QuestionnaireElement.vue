<script setup lang="ts">
import {useId, ref, computed, onMounted, watch, Ref, inject} from 'vue'
import QuestionnaireRowElement from "./QuestionnaireRowElement.vue";
import {
  i18n_any,
  QUESTION_TYPE,
  QUESTION_TYPE_LABEL,
  QUESTIONNAIRE_TYPE,
  QUESTIONNAIRE_TYPE_LABEL, setListState,
  SYSTEM_DATAFIELDS, TYPES_ALLOWED_AS_DEPENDENCIES
} from "./helper";
import { gettext } from './gettextstub';
import I18nTextField from "./I18nTextField.vue";
import NativeDialog from "./NativeDialog.vue";
import { SlickList, SlickItem, DragHandle } from 'vue-slicksort';
import {getDatafieldCreateUrl} from "./api";
import DjangoDialog from "./DjangoDialog.vue";
import * as api from './api';
import QuestionnaireEditForm from "./QuestionnaireEditForm.vue";
import SalesChannelIcon from "./SalesChannelIcon.vue";
import {SalesChannel} from "./model";
import I18nTextArea from "./I18nTextArea.vue";

const dlgEditor = ref()
const dlgAddExisting = ref()
const dlgAddTextblock = ref()
const dlgNewDatafield = ref()

const newTextblockTitle = ref()
const newTextblockText = ref()

const id = useId();
const props = defineProps(['questionnaire', 'datafields', 'selected_product', 'grouped_items', 'preview_mode', 'err_mes'])
const emit = defineEmits(['update', 'invalidate:datafields', 'invalidate:questionnaires'])
const sales_channels: Ref<SalesChannel[]> = inject('pretix:env:organizer:sales_channels')

let nextId = 1;
watch(() => props.questionnaire.rows, () => {
	for (let qc of props.questionnaire.rows) {
		if (!qc._cid) qc._cid = id + (++nextId);
	}
})

function addExistingDatafield (...fields) {
  for (const field of fields) {
    if (askedDatafields.value.has(field.identifier)) continue;
    props.questionnaire.rows.push({
      _cid: useId(),
      datafield: field.identifier,
      required: false,
      label: field.question ?? {en: field.internal_name},
      help_text: {},
      dependency_datafield: null,
      dependency_values: [],
    })
  }
	dlgAddExisting.value.close()
	emit('update')
}

function showAddTextblockDialog () {
	newTextblockTitle.value = {}
	newTextblockText.value = {}
	dlgAddTextblock.value.show()
}

function addTextblock () {
	props.questionnaire.rows.push({
		_cid: useId(),
		datafield: null,
		required: false,
		label: newTextblockTitle.value,
		help_text: newTextblockText.value,
		dependency_datafield: null,
		dependency_values: [],
	})
	dlgAddTextblock.value.close()
	emit('update')
}

function newDatafield () {
	dlgNewDatafield.value.open(getDatafieldCreateUrl(props.questionnaire.type.startsWith('order_') ? 'O' : 'P'))
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
const askedDatafields = computed(() => new Set(props.questionnaire.rows.map(row => row.datafield)))
const addressFieldIdentifiers = new Set(['@street', '@city', '@zipcode', '@state', '@country'])
const anyAddressFieldAsked = computed(() => addressFieldIdentifiers.intersection(askedDatafields.value).size > 0)
const allAddressFieldsAsked = computed(() => addressFieldIdentifiers.isSubsetOf(askedDatafields.value))
const allAddressFields = computed(() => props.datafields.filter(df => addressFieldIdentifiers.has(df.identifier)))

</script>

<style>
.sales-channel-icons > * { margin-left: 4px; opacity: 0.8; }
.list-group-item.exists, .list-group-item.exists:hover { color: #666; text-decoration: line-through; background: #fcfcfc; cursor: default; }
details > summary.list-group-item { color: #666; padding: 5px 15px 5px 28px; }
details .list-group-item { padding-left: 28px }
details > summary.list-group-item:hover { color: #555; text-decoration: none; background-color: #f5f5f5; }
details > summary.list-group-item::before {
    position: absolute;
    top: 50%;
    left: 10px;
    margin-top: -.5em;
    content: "";
    width: 1em;
    height: 1em;
    font: normal normal normal 14px/1 FontAwesome;
    display: inline-block;
    text-align: center;
    transform: rotate(-90deg);
    transition: transform 150ms ease-in 0s;
}
details[open] > summary.list-group-item::before {
    transform: rotate(0deg);
}
details[open] > summary.list-group-item {
    color: black;
}
</style>

<template>

  <details class="questionnaire-panel" :open="preview_mode"
    :class="{ 'hidden-questionnaire': isHidden }">
    <summary class="questionnaire-panel-heading">
			<div class=" editor-row">
				<div class="editor-preview-area">
					<input type="checkbox" @change="e => {setListState(props.questionnaire.items, (e.target as HTMLInputElement).checked, selected_product); emit('update')}" v-if="selected_product && !preview_mode" :checked="!isHidden">
					{{ props.questionnaire.internal_name }}
          <span v-if="questionnaire.compat_personalization">
            <span class="text-muted fa fa-fw fa-id-card-o" data-toggle="tooltip" :title="gettext('Default questionnaire for creating personalized items via legacy API')"></span>
          </span>
					<span class="fa fa-warning" v-if="questionnaire._err_mes"></span>
					<span class="fa fa-cog fa-spin" v-if="questionnaire._loading"></span>

          <span class="pull-right" v-if="questionnaire.type === 'position_checkin'">
            <span class="label label-default" data-toggle="tooltip" :title="gettext('Ask during check-in')">
              <span class="fa fa-check-square"></span>
              {{ gettext('Check-in') }}</span>
          </span>
          <span class="pull-right" v-else-if="questionnaire.type === 'position_attendee'">
            <span class="label label-default">{{ gettext('Attendee link') }}</span>
          </span>
          <span class="pull-right" v-else-if="questionnaire.type === 'position_hidden'">
            <span class="label label-default" data-toggle="tooltip" :title="gettext('Hidden question')">
              <span class="fa fa-eye-slash"></span>
              {{ gettext('Hidden') }}
            </span>
          </span>
          <span class="pull-right sales-channel-icons" v-else>
            <template v-for="sc in sales_channels">
              <SalesChannelIcon
                  v-if="props.questionnaire.all_sales_channels || props.questionnaire.limit_sales_channels.indexOf(sc.identifier) !== -1"
                  :sales-channel="sc" :tooltip="true" />
            </template>
          </span>
				</div>

				<aside class="editor-action-area"><div class="btn-group">
					<a v-drag-handle class="btn btn-default drag-handle" v-if="!preview_mode" :title="gettext('Click and drag this button to reorder.')"><i class="fa fa-arrows"></i></a>
					<button class="btn btn-default" @click="dlgEditor.show()" :title="`#${questionnaire.id}`"><i class="fa fa-wrench"></i></button>
				</div></aside>
			</div>
    </summary>
    <div class="questionnaire-panel-body" v-if="!isHidden">
			<div class="alert alert-warning" v-if="questionnaire._err_mes">
        <dl v-if="questionnaire._err_mes.api_error">
          <template v-for="(messages, key) in questionnaire._err_mes.api_error">
            <dt>{{ key }}</dt>
            <dd><ul><li v-for="message in messages">{{ message }}</li></ul></dd>
          </template>
        </dl>
        <p v-else>{{ questionnaire._err_mes }}</p>
      </div>
      <div class="form-horizontal" :id="`questionListParent${props.questionnaire.id}`">
				<SlickList axis="y" v-model:list="props.questionnaire.rows" useDragHandle helperClass="drag-helper" :appendTo="`#questionListParent${props.questionnaire.id}`" @update:list="emit('update')">
					<SlickItem v-for="(child, index) in props.questionnaire.rows" :key="child._cid" :index="index">
						<QuestionnaireRowElement
										:datafields="props.datafields"
										:question="child"
										:editable="true"
										:possible_dependencies="props.questionnaire.rows.slice(0, index).filter(row => TYPES_ALLOWED_AS_DEPENDENCIES.has(props.datafields.find(el => el.identifier === row.datafield)?.type))"
										@remove-self="questionnaire.rows.splice(index, 1); emit('update')"
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
								<button class="btn btn-default" @click="newDatafield()"><i class="fa fa-plus"></i> {{ gettext('New data field') }}</button>
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
			<QuestionnaireEditForm :questionnaire="questionnaire" :grouped_items="grouped_items"/>

			<button @click="dlgEditor.close(); emit('update')" class="btn btn-primary pull-right"><span class="fa fa-check"></span> {{ gettext('Save and close') }}</button>
			<button @click="deleteQuestionnaire" class="btn btn-default">{{ gettext('Delete') }}</button>
    </NativeDialog>

    <NativeDialog ref="dlgAddExisting" class="modal-card"
                  :title="gettext('Add existing data field')">

        <h4>{{ gettext('System fields') }}</h4>
				<div class="list-group">
          <template v-for="field in datafields">
					  <a v-if="field.identifier.startsWith('@') && !addressFieldIdentifiers.has(field.identifier)"
               href="javascript:" @click="addExistingDatafield(field)"
               :class="`list-group-item ${askedDatafields.has(field.identifier) ? 'exists' : ''}`">{{ i18n_any(field.question) }}</a>
          </template>

          <a v-if="allAddressFields.length"
              href="javascript:" @click="addExistingDatafield(...allAddressFields)"
             :class="`list-group-item ${anyAddressFieldAsked ? 'exists' : ''}`">{{ gettext('Attendee address') }}</a>
          <details v-if="allAddressFields.length" :open="anyAddressFieldAsked && !allAddressFieldsAsked">
            <summary class="list-group-item">{{ gettext('Individual address fields ...') }}</summary>

            <template v-for="field in datafields">
              <a v-if="addressFieldIdentifiers.has(field.identifier)"
                 href="javascript:" @click="addExistingDatafield(field)"
                 :class="`list-group-item ${askedDatafields.has(field.identifier) ? 'exists' : ''}`">{{ i18n_any(field.question) }}</a>
            </template>
          </details>
				</div>

        <h4>{{ gettext('User-defined data fields') }}</h4>
				<div class="list-group">
          <template v-for="field in datafields">
					  <a v-if="!field.identifier.startsWith('@')"
               href="javascript:" @click="addExistingDatafield(field)"
               :class="`list-group-item ${askedDatafields.has(field.identifier) ? 'exists' : ''}`">{{ field.internal_name }}</a>
          </template>
        </div>

        <button @click="dlgAddExisting.close()" class="btn btn-default pull-right">{{ gettext('Cancel') }}</button>
    </NativeDialog>

    <NativeDialog ref="dlgAddTextblock" class="modal-card"
                  :title="gettext('Add text block')">

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
            <I18nTextArea :value="newTextblockText"/>
          </div>
        </div>

        <button @click="addTextblock()" class="btn btn-primary pull-right"><span class="fa fa-check"></span> {{ gettext('OK') }}</button>
        <button @click="dlgAddTextblock.close()" class="btn btn-default">{{ gettext('Cancel') }}</button>

    </NativeDialog>

		<DjangoDialog ref="dlgNewDatafield" @confirm="onNewDatafieldCreated" max-width="60em"></DjangoDialog>
  </Teleport>
</template>
