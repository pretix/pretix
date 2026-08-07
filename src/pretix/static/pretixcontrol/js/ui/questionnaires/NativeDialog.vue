<script setup lang="ts">
import { ref, useId } from 'vue';

const dialog = ref<HTMLDialogElement>();

const props = defineProps({
  classes: {
    type: String,
    default: "",
  },
  title: '',
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
    ref="dialog" class="modal-card"
    @close="visible = false"
    closedby="any"
    :aria-labelledby="`${id}-title`"
  >
    <form
      v-if="visible"
      method="dialog" class="modal-card-inner form-horizontal"
      :class="{
        [props.classes]: props.classes,
      }"
    >
      <div class="modal-card-content">
          <h2 :id="`${id}-title`" class="modal-card-title h3">{{ title }}</h2>
          <slot />
      </div>
    </form>
  </dialog>
</template>
