<script setup lang="ts">
import { ref, useId } from 'vue';

const dialog = ref<HTMLDialogElement>();

const props = defineProps({
  classes: {
    type: String,
    default: "",
  },
  title: {type: String, default: ''},
	noPadding: {type: Boolean, default: false},
	noScroll: {type: Boolean, default: true},
	maxWidth: {type: String, default: '43em'},
});

const visible = ref(false);

const showModal = () => {
  dialog.value?.showModal();
  visible.value = true;
};

defineExpose({
  show: showModal,
  close: (returnVal?: string): void => dialog.value?.close(returnVal),
  visible,
});
const id = useId();
</script>

<template>
  <dialog
    ref="dialog" :class="`modal-card ${props.noPadding ? 'no-padding' : ''} ${props.noPadding ? 'no-scroll' : ''}`"
    @close="visible = false"
    closedby="any"
    :aria-labelledby="`${id}-title`"
		:style="{maxWidth: props.maxWidth}"
  >
    <form
      v-if="visible"
      method="dialog" class="modal-card-inner form-horizontal"
      :class="{
        [props.classes]: props.classes,
      }"
    >
      <div class="modal-card-content">
          <h2 :id="`${id}-title`" class="modal-card-title h3" v-if="title">{{ title }}</h2>
          <slot />
      </div>
    </form>
  </dialog>
</template>

<style>
.modal-card.no-padding, .modal-card.no-padding .modal-card-content { padding: 0; }
.modal-card.no-scroll { overflow: hidden; }
</style>
