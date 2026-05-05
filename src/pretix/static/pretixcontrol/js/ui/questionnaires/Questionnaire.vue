<script setup lang="ts">
import {useId, ref, computed} from 'vue'
import Question from "./Question.vue";
import {i18n_any, QUESTION_TYPE, QUESTION_TYPE_LABEL} from "./helper";
import I18nTextField from "./I18nTextField.vue";
import NativeDialog from "./NativeDialog.vue";
import { SlickList, SlickItem, DragHandle } from 'vue-slicksort';

const dlgEditor = ref();
const dlgAddExisting = ref();
const dlgAddTextblock = ref();

const newTextblockTitle = ref();
const newTextblockText = ref();

const id = useId();
const props = defineProps(['questionnaire', 'datafields', 'selected_product', 'items'])
const gettext = (window as any).gettext

function toggleItem() {
  const i = props.questionnaire.items.indexOf(props.selected_product);
  if (i === -1) {
    props.questionnaire.items.push(props.selected_product);
  } else {
    props.questionnaire.items.splice(i, 1);
  }
}

function addExistingDatafield(field) {
	props.questionnaire.children.push({
		question: field.id,
		required: false,
		label: {},
		help_text: {},
		dependency_question: null,
		dependency_values: [],
	});
	dlgAddExisting.value.close();
}

function showAddTextblockDialog() {
	newTextblockTitle.value = {};
	newTextblockText.value = {};
	dlgAddTextblock.value.show();
}

function addTextblock() {
	props.questionnaire.children.push({
		question: null,
		required: false,
		label: newTextblockTitle.value,
		help_text: newTextblockText.value,
		dependency_question: null,
		dependency_values: [],
	});
	dlgAddTextblock.value.close();
}

const isHidden = computed(() => props.selected_product && props.questionnaire.items.indexOf(props.selected_product) === -1);
const isEditable = computed(() => props.selected_product && props.questionnaire.items.indexOf(props.selected_product) !== -1);

</script>


<template>
	<div class="question-edit-buttons"><div>
		<DragHandle tag="button" class="btn btn-default"><i class="fa fa-arrows"></i></DragHandle>
		<button class="btn btn-default" @click="dlgEditor.show()"><i class="fa fa-edit"></i></button>
		<button class="btn btn-default" @click="toggleItem()" v-if="selected_product"><i :class="`fa fa-eye${isHidden ? '-slash':''}`"></i></button>
	</div></div>

  <details class="panel panel-default " :open="!!isEditable"
    :class="{ 'hidden-question': isHidden }">
    <summary class="panel-heading">
			{{ props.questionnaire.internal_name }}
    </summary>
    <div class="panel-body" v-if="!isHidden">
      <div class="form-horizontal" :id="`questionListParent${props.questionnaire.id}`">

				<SlickList axis="y" v-model:list="props.questionnaire.children" useDragHandle :appendTo="`#questionListParent${props.questionnaire.id}`">
					<SlickItem v-for="(child, index) in props.questionnaire.children" :key="child.id" :index="index">
						<Question
										:datafields="props.datafields"
										:question="child"
										:editable="true"
										@remove-self="questionnaire.children.splice(index, 1)" />
					</SlickItem>
				</SlickList>

      </div>
			<p v-if="true">
					<button class="btn btn-default" @click="dlgAddExisting.show()"><i class="fa fa-plus"></i> {{ gettext('Existing data field') }}</button>
					<button class="btn btn-default" @click="newDatafield()"><i class="fa fa-plus"></i> {{ gettext('New data field') }}</button>
					<button class="btn btn-default" @click="showAddTextblockDialog()"><i class="fa fa-plus"></i> {{ gettext('Text') }}</button>
			</p>
    </div>
  </details>

  <Teleport to="body">
    <NativeDialog ref="dlgEditor" class="modal-card"
                  :title="gettext('Edit questionnaire')">
        <div class="form-group">
          <label class="col-md-3 control-label">
            {{ gettext('Internal name') }}
          </label>
          <div class="col-md-9">
            <input type="text" class="form-control" v-model="questionnaire.internal_name"/>
          </div>
        </div>
        <div class="form-group">
          <label class="col-md-3 control-label">
            {{ gettext('Visible on products') }}
          </label>
          <div class="col-md-9">
						<div class="checkbox" v-for="item in items">
							<label :for="id + '_' + item.id">
								<input :id="id + '_' + item.id" type="checkbox" :checked="questionnaire.items.indexOf(item.id) !== -1"> {{ item.internal_name || i18n_any(item.name) }}
							</label>
						</div>
          </div>
        </div>
        <button @click="dlgEditor.close()" class="btn btn-primary pull-right"><span class="fa fa-check"></span> {{ gettext('Save and close') }}</button>
        <button class="btn btn-default">{{ gettext('Delete') }}</button>
    </NativeDialog>

    <NativeDialog ref="dlgAddExisting" class="modal-card"
                  :title="gettext('Add existing data field')">

				<div class="list-group">
					<a href="javascript:" @click="addExistingDatafield(field)" v-for="field in datafields" class="list-group-item">{{ field.internal_name }}</a>
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
  </Teleport>
</template>
