<script setup lang="ts">

import {gettext} from "./gettextstub";
import NativeDialog from "./NativeDialog.vue";
import {computed, onMounted, onUnmounted, ref, watch} from "vue";

const props = defineProps(['defaultUrl'])
const emit = defineEmits(['confirm'])
const dlgDjangoDialog = ref()
const url = ref(props.defaultUrl)
const frameHeight = ref(400)
const frameLoading = ref(true)

function messageEvent(e: MessageEvent) {
	console.log('messageEvent', e.origin, e.source, e.data)
	if (!dlgDjangoDialog.value.visible) return
	if (e.origin === location.origin && e.data.type === 'pretix:dialog-loaded') {
		frameHeight.value = Math.min(window.innerHeight - 120, e.data.contentHeight|0)
		frameLoading.value = false
	}
	if (e.origin === location.origin && e.data.type === 'pretix:notify-parent') {
		dlgDjangoDialog.value.close()
		emit('confirm', e.data.data)
		if (e.data.data.messages) {
			alert(e.data.data.messages.map(m => m.message).join('\n\n'))
		}
	}
}
onMounted(() => {
	window.addEventListener('message', messageEvent)
})
onUnmounted(() => {
	window.removeEventListener('message', messageEvent)
})

defineExpose({
  dialog: dlgDjangoDialog,
	open: (newUrl) => {
		frameLoading.value = true
		frameHeight.value = 400
		url.value = newUrl
		dlgDjangoDialog.value.show()
	}
});
</script>

<template>
    <NativeDialog ref="dlgDjangoDialog" class="modal-card" no-padding="true" no-scroll="true">
			<div :style="{'height': frameHeight + 'px'}">
        <i class="fa fa-cog big-rotating-icon" v-if="frameLoading"></i>
				<iframe :src="url" v-if="dlgDjangoDialog.visible" :height="frameHeight" :style="{'visibility': frameLoading ? 'hidden' : 'visible'}"></iframe>
			</div>
    </NativeDialog>
</template>

<style scoped>
div { text-align: center; }
iframe { width: 100%; border: 0; }
</style>
