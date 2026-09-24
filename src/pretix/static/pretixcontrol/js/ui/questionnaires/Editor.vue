<script setup lang="ts">
import QuestionnaireElement from './QuestionnaireElement.vue';
import * as api from './api';
import {Datafield, Questionnaire} from './model';
import {i18n_any, sort, numericComp, groupBy, SYSTEM_DATAFIELDS} from './helper';
import { gettext } from './gettextstub';
import {inject, onMounted, onUnmounted, ref} from 'vue';
import { SlickList, SlickItem } from 'vue-slicksort';
import { ProgressBar } from "./ProgressBar";

const grouped_items = inject('pretix:env:event:grouped_items')

type QuestionnaireMaybeUnsaved = Omit<Questionnaire, 'id'> & { _new_id?: number, id?: number };
const order_questionnaires = ref<QuestionnaireMaybeUnsaved[]>();
const position_questionnaires = ref<QuestionnaireMaybeUnsaved[]>();
const order_datafields = ref<Datafield[]>();
const position_datafields = ref<Datafield[]>();

let lastDataRefresh = 0
async function refreshQuestionnaireList () {
	const all_questionnaires: QuestionnaireMaybeUnsaved[] = await api.getQuestionnaires();

	order_questionnaires.value = all_questionnaires.filter(q => q.type.startsWith('O'))
	position_questionnaires.value = all_questionnaires.filter(q => q.type.startsWith('P'))
	lastDataRefresh = Date.now()
}
async function refreshDatafieldList () {
	order_datafields.value = await api.getDatafields('O')
	position_datafields.value = (await api.getDatafields('P')).concat(Object.values(SYSTEM_DATAFIELDS))
	console.log('datafield list refreshed')
}
await Promise.all([refreshQuestionnaireList(), refreshDatafieldList()])

function saveQuestionnaire(questionnaire) {
	let result;
	questionnaire._loading = true
	if (questionnaire.id) {
		result = api.updateQuestionnaire(questionnaire.id, questionnaire)
	} else {
		result = api.createQuestionnaire(questionnaire)
	}
	result = result.then(d => {
		questionnaire.id = d.id
		questionnaire.children = d.children
		questionnaire._err_mes = null
		questionnaire._loading = false
		return d;
	}, err => {
		questionnaire._err_mes = err
		questionnaire._loading = false
		return err;
	})
	return result;
}
function addPositionQuestionnaire () {
	position_questionnaires.value.push({
		all_sales_channels: true, children: [], limit_sales_channels: [], position: 0,
		items: [], internal_name: "Unnamed questionnaire", type: "PS",
		_new_id: Date.now(),
	});
}
function addOrderQuestionnaire () {
	order_questionnaires.value.push({
		all_sales_channels: true, children: [], limit_sales_channels: [], position: 0,
		items: [], internal_name: "Unnamed questionnaire", type: "OS",
		_new_id: Date.now(),
	});
}
async function saveData () {
	using pb = ProgressBar.show('saving questionnaires')
	let promises = [];
	let i = 0;
	for (const questionnaire of order_questionnaires.value) {
		questionnaire.position = i++;
		promises.push(saveQuestionnaire(questionnaire))
	}
	i = 0;
	for (const questionnaire of position_questionnaires.value) {
		questionnaire.position = i++;
		promises.push(saveQuestionnaire(questionnaire))
	}
	await Promise.all(promises)
}
/*
export default {
	components: {
		QuestionnaireElement, SlickList, SlickItem,
	},
	methods: {
		i18n_any,
	},
	data() {
		return {
			order_questionnaires,
			position_questionnaires,
			order_datafields,
			position_datafields,
			items: items_list,
			grouped_items,
			categories,

		}
	}
}*/

function windowFocused() {
	if (Date.now() - lastDataRefresh > 30000) {
		if (document.querySelector("dialog[open]")) {
			// TODO this should not be skipped completely but handled in a more robust way
			// currently dialogs are very flaky if the whole questionnaires list gets replaced underneath
			// them (they will stay open, but saving them will cause weird problems i don't fully understand yet)
			console.log('skipping refresh because a dialog is open')
			return
		}
		console.log('refreshing to avoid overwriting with older data on edit')
		refreshQuestionnaireList()
	}
}
onMounted(() => window.addEventListener('focus', windowFocused))
onUnmounted(() => window.removeEventListener('focus', windowFocused))

const selected_product = ref("")
const preview_mode = ref(false)
</script>

<style>
.hidden-questionnaire { opacity: 0.3; }

.questionnaires-list {
	padding: 20px 190px 20px 0;
	background: linear-gradient(to right, #fff 0, #fff calc(100% - 172px), #ddd calc(100% - 171px), #f6f2f8 calc(100% - 171px), #fff calc(100% - 100px), #fff 100%);
}
.question-edit-buttons { float:right; }
.question-edit-buttons div { position: absolute; margin-left: 10px; min-width: 100px;  }
.question-edit-buttons button {  }
.form-group { margin-bottom: 30px }

.questionnaires-editor.product-selected .questionnaire-panel .questionnaire-panel-heading {}

.questionnaires-editor:not(.preview-mode) .questionnaire-panel .questionnaire-panel-heading .editor-row { border-top: 1px solid rgb(175 175 175 / 0.3); 	 }
.questionnaires-editor:not(.preview-mode) .questionnaire-panel[open] .questionnaire-panel-heading .editor-row { border-bottom: 1px solid rgb(216 216 216 / 0.3);  }

.questionnaires-editor.preview-mode .questionnaire-panel .questionnaire-panel-heading { color: #888; margin-top: 5px; border-top: 1px dashed rgb(175 175 175 / 0.3); border-bottom: 1px dashed rgb(216 216 216 / 0.3); font-style: italic; padding: 0; }

.questionnaires-editor .editor-row:not(:hover) .btn.btn-default,
.questionnaires-editor .editor-action-row:not(:hover) .btn.btn-default{ box-shadow: 0 0 0 0 #eeeeee; background: transparent; color: #555; }

.filter-row { background: #f8e6ff; border: 1px solid #e3cbed; padding: 10px; }

.debuginfo { font-size: 70%; background: rgba(200, 200, 200, 0.5); }
.dependency-info { position: absolute;  }
.dependency-info > span {  }

.category-header { margin: 8px 0 -5px 0; font-weight: bold; color: #737373; }

.editor-row { display: flex; width: calc(100% + 190px); background: transparent; }
.editor-row:hover { background: rgba(255,233,244,0.3); }
.editor-preview-area { flex: 1; padding-left: 10px; padding-right: 40px; }
.editor-action-area { width: 160px; padding-left: 20px; }
.questionnaire-panel-heading .editor-preview-area { padding-block: 11px; }
.questionnaire-panel-heading .editor-action-area { padding-block: 5px; }
.questionnaire-panel-body .editor-preview-area, .questionnaire-panel-body .editor-action-area { padding-block: 10px; }
.preview-mode .editor-preview-area { padding-right: 50px; }

.questionnaires-editor.questionnaires-editor .form-group { margin-bottom: 0px; }

.questionnaire-panel .questionnaire-panel-heading .editor-preview-area::before {
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
.questionnaire-panel[open] .questionnaire-panel-heading .editor-preview-area::before {
    transform: rotate(0deg);
}

.editor-action-row { padding-top: 10px; width: calc(100% + 190px); padding-right: 170px }
.questionnaires-list > .editor-action-row { border-top: 1px solid rgb(175 175 175 / 0.3); padding-top: 25px; padding-bottom: 10px }
</style>
<template>
	<div class="questionnaires-editor" v-if="!preview_mode">
		<div class="filter-row">
			Order questionnaires
		</div>
		<div class="questionnaires-list">
			<SlickList axis="y" v-model:list="order_questionnaires" useDragHandle appendTo="#orderQuestionnaireListParent" id="orderQuestionnaireListParent" @update:list="saveData()">
				<SlickItem v-for="(questionnaire, index) in order_questionnaires" :key="questionnaire.id || questionnaire._new_id" :index="index">
					<QuestionnaireElement
						:questionnaire="questionnaire"
						:datafields="order_datafields"
						:grouped_items="null"
						:selected_product="null"
						:preview_mode="false"
						@update="saveQuestionnaire(questionnaire)"
						@invalidate:datafields="refreshDatafieldList()"
						@invalidate:questionnaires="refreshQuestionnaireList()"/>
				</SlickItem>
			</SlickList>
			<div class="editor-action-row form-horizontal">
				<div class="form-group">
					<div class="col-md-9 col-md-push-3">
						<button class="btn btn-default" @click="addOrderQuestionnaire()"><i class="fa fa-plus"></i> {{ gettext('New questionnaire') }}</button>
					</div>
				</div>
			</div>
		</div>
	</div>

	<div :class="`questionnaires-editor ${selected_product ? 'product-selected':''} ${preview_mode ? 'preview-mode':''}`">
		<div class="filter-row" v-if="preview_mode">
			<button class="btn btn-default" @click="preview_mode = false"><span class="fa fa-chevron-left"></span> {{ gettext('Back') }}</button>
			Previewing questionnaires for product {{ selected_product }}
		</div>
		<div class="filter-row" v-else>
			Questionnaires for product:
			<select v-model="selected_product">
				<option value="">(all)</option>
				<optgroup v-for="[category, items] in grouped_items" :label="category.internal_name || i18n_any(category.name)">
					<option v-for="item in items" :value="item.id">
						{{ item.internal_name || i18n_any(item.name) }}
					</option>
				</optgroup>
			</select>
			&nbsp;
			<button class="btn btn-default" @click="preview_mode = true" :disabled="!selected_product"> {{ gettext('Preview') }}</button>
		</div>

		<div class="questionnaires-list" v-if="preview_mode && selected_product">
			<details class="panel panel-default details-open" open>
				<summary class="panel-heading">
					<h4 class="panel-title">
						<strong>Product {{ selected_product }}</strong>
					</h4>
				</summary>

				<QuestionnaireElement v-for="(questionnaire, index) in position_questionnaires.filter(q => q.items.indexOf(selected_product as any) !== -1)"
					:questionnaire="questionnaire"
					:datafields="position_datafields"
					:grouped_items="grouped_items"
					:selected_product="selected_product"
					:preview_mode="true"
					@update="saveQuestionnaire(questionnaire)"
					@invalidate:datafields="refreshDatafieldList()"
					@invalidate:questionnaires="refreshQuestionnaireList()"/>
			</details>
		</div>

		<div class="questionnaires-list" v-else>
			<SlickList axis="y" v-model:list="position_questionnaires" useDragHandle appendTo="#questionnaireListParent" id="questionnaireListParent" @update:list="saveData()">
				<SlickItem v-for="(questionnaire, index) in position_questionnaires" :key="questionnaire.id || questionnaire._new_id" :index="index">
					<QuestionnaireElement
						:questionnaire="questionnaire"
						:datafields="position_datafields"
						:grouped_items="grouped_items"
						:selected_product="selected_product"
						:preview_mode="false"
						@update="saveQuestionnaire(questionnaire)"
						@invalidate:datafields="refreshDatafieldList()"
						@invalidate:questionnaires="refreshQuestionnaireList()"/>
				</SlickItem>
			</SlickList>
			<div v-if="!preview_mode" class="editor-action-row form-horizontal">
				<div class="form-group">
					<div class="col-md-9 col-md-push-3">
						<button class="btn btn-default" @click="addPositionQuestionnaire()"><i class="fa fa-plus"></i> {{ gettext('New questionnaire') }}</button>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>
