<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted, inject, nextTick } from 'vue'
import { StoreKey } from '~/sharedStore'
import { STRINGS } from '~/i18n'

const store = inject(StoreKey)!

const cancelBlocked = ref(false)
const lightboxImage = ref<HTMLImageElement>()
const frameDialog = ref<HTMLDialogElement>()
const alertDialog = ref<HTMLDialogElement>()
const lightboxDialog = ref<HTMLDialogElement>()
const iframe = ref<HTMLIFrameElement>()
const closeButton = ref<HTMLButtonElement>()

const frameClasses = computed(() => ({
	'pretix-widget-frame-holder': true,
	'pretix-widget-frame-shown': store.overlay.frameShown || store.overlay.frameLoading,
	'pretix-widget-frame-isloading': store.overlay.frameLoading,
}))

const alertClasses = computed(() => ({
	'pretix-widget-alert-holder': true,
	'pretix-widget-alert-shown': store.overlay.errorMessage,
}))

const lightboxClasses = computed(() => ({
	'pretix-widget-lightbox-holder': true,
	'pretix-widget-lightbox-shown': store.overlay.lightbox,
	'pretix-widget-lightbox-isloading': store.overlay.lightbox?.loading,
}))

const cancelBlockedClasses = computed(() => ({
	'pretix-widget-visibility-hidden': !cancelBlocked.value,
}))

const errorMessageId = computed(() => `${store.htmlId}-error-message`)

function onMessage (e: MessageEvent) {
	if (e.data.type && e.data.type === 'pretix:widget:title') {
		if (iframe.value) {
			iframe.value.title = e.data.title
		}
	}
}

function lightboxClose () {
	store.overlay.lightbox = null
}

function lightboxLoaded () {
	if (store.overlay.lightbox) {
		store.overlay.lightbox.loading = false
	}
}

function errorClose (e: Event) {
	const dialog = e.target as HTMLDialogElement
	if (dialog.returnValue === 'continue' && store.overlay.errorUrlAfter) {
		if (store.overlay.errorUrlAfterNewTab) {
			window.open(store.overlay.errorUrlAfter)
		} else {
			store.overlay.frameSrc = store.overlay.errorUrlAfter
			store.overlay.frameLoading = true
		}
	}
	store.overlay.errorMessage = null
	store.overlay.errorUrlAfter = null
	store.overlay.errorUrlAfterNewTab = false
}

function close () {
	if (store.overlay.frameLoading) {
		frameDialog.value?.showModal()
		return
	}
	store.overlay.frameShown = false
	store.frameDismissed = true
	store.overlay.frameSrc = ''
	store.reload()
	triggerCloseCallback()
}

function cancel (e: Event) {
	if (store.overlay.frameLoading) {
		e.preventDefault()
		const target = e.target as HTMLElement
		target.addEventListener('animationend', function () {
			target.classList.remove('pretix-widget-shake-once')
		}, { once: true })
		target.classList.add('pretix-widget-shake-once')
		cancelBlocked.value = true
	}
}

function iframeLoaded () {
	if (store.overlay.frameLoading) {
		store.overlay.frameLoading = false
		cancelBlocked.value = false
		if (store.overlay.frameSrc) {
			store.overlay.frameShown = true
		}
	}
}

function triggerCloseCallback () {
	nextTick(() => {
		for (const callback of (window as any).PretixWidget._closed || []) {
			callback()
		}
	})
}

watch(() => store.overlay.lightbox, (newValue, oldValue) => {
	if (newValue) {
		if (newValue.image !== oldValue?.image) {
			newValue.loading = true
		}
		if (!oldValue) {
			lightboxDialog.value?.showModal()
		}
	}
})

watch(() => store.overlay.errorMessage, (newValue, oldValue) => {
	if (newValue && !oldValue) {
		alertDialog.value?.showModal()
	}
})

watch(() => store.overlay.frameShown, (newValue) => {
	if (newValue) {
		nextTick(() => {
			closeButton.value?.focus()
		})
	}
})

watch(() => store.overlay.frameSrc, (newValue, oldValue) => {
	if (newValue && !oldValue) {
		store.overlay.frameLoading = true
	}
	if (iframe.value) {
		iframe.value.src = newValue || 'about:blank'
	}
})

watch(() => store.overlay.frameLoading, (newValue) => {
	if (newValue) {
		if (frameDialog.value && !frameDialog.value.open) {
			frameDialog.value.showModal()
		}
	} else {
		if (!store.overlay.frameSrc && frameDialog.value?.open) {
			frameDialog.value.close()
		}
	}
})

onMounted(() => {
	window.addEventListener('message', onMessage, false)
})

onUnmounted(() => {
	window.removeEventListener('message', onMessage, false)
})
</script>

<template lang="pug">
Teleport(to="body")
	.pretix-widget-overlay
		//- Iframe dialog
		dialog(ref="frameDialog", :class="frameClasses", :aria-label="STRINGS.checkout", @close="close", @cancel="cancel")
			.pretix-widget-frame-loading(v-show="store.overlay.frameLoading")
				svg(width="256", height="256", viewBox="0 0 1792 1792", xmlns="http://www.w3.org/2000/svg")
					path.pretix-widget-primary-color(d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z")
				p(:class="cancelBlockedClasses")
					strong {{ STRINGS.cancel_blocked }}
			.pretix-widget-frame-inner(v-show="store.overlay.frameShown")
				form.pretix-widget-frame-close(method="dialog")
					button(ref="closeButton", :aria-label="STRINGS.close_checkout", autofocus)
						svg(:alt="STRINGS.close", height="16", viewBox="0 0 512 512", width="16", xmlns="http://www.w3.org/2000/svg")
							path(fill="#fff", d="M437.5,386.6L306.9,256l130.6-130.6c14.1-14.1,14.1-36.8,0-50.9c-14.1-14.1-36.8-14.1-50.9,0L256,205.1L125.4,74.5 c-14.1-14.1-36.8-14.1-50.9,0c-14.1,14.1-14.1,36.8,0,50.9L205.1,256L74.5,386.6c-14.1,14.1-14.1,36.8,0,50.9 c14.1,14.1,36.8,14.1,50.9,0L256,306.9l130.6,130.6c14.1,14.1,36.8,14.1,50.9,0C451.5,423.4,451.5,400.6,437.5,386.6z")
				iframe(
					ref="iframe",
					frameborder="0",
					width="650",
					height="650",
					:name="store.widgetId",
					src="about:blank",
					allow="autoplay *; camera *; fullscreen *; payment *",
					:title="STRINGS.checkout",
					referrerpolicy="origin",
					@load="iframeLoaded"
				) Please enable frames in your browser!

		//- Alert dialog
		dialog(ref="alertDialog", :class="alertClasses", role="alertdialog", :aria-labelledby="errorMessageId", @close="errorClose")
			form.pretix-widget-alert-box(method="dialog")
				p(:id="errorMessageId") {{ store.overlay.errorMessage }}
				p
					button(v-if="store.overlay.errorUrlAfter", value="continue", autofocus, :aria-describedby="errorMessageId")
						| {{ STRINGS.continue }}
					button(v-else, autofocus, :aria-describedby="errorMessageId") {{ STRINGS.close }}
			transition(name="bounce")
				svg.pretix-widget-alert-icon(v-if="store.overlay.errorMessage", width="64", height="64", viewBox="0 0 1792 1792", xmlns="http://www.w3.org/2000/svg")
					path(style="fill:#ffffff;", d="M 599.86438,303.72882 H 1203.5254 V 1503.4576 H 599.86438 Z")
					path.pretix-widget-primary-color(d="M896 128q209 0 385.5 103t279.5 279.5 103 385.5-103 385.5-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103zm128 1247v-190q0-14-9-23.5t-22-9.5h-192q-13 0-23 10t-10 23v190q0 13 10 23t23 10h192q13 0 22-9.5t9-23.5zm-2-344l18-621q0-12-10-18-10-8-24-8h-220q-14 0-24 8-10 6-10 18l17 621q0 10 10 17.5t24 7.5h185q14 0 23.5-7.5t10.5-17.5z")

		//- Lightbox dialog
		dialog(ref="lightboxDialog", :class="lightboxClasses", role="alertdialog", @close="lightboxClose")
			.pretix-widget-lightbox-loading(v-if="store.overlay.lightbox?.loading")
				svg(width="256", height="256", viewBox="0 0 1792 1792", xmlns="http://www.w3.org/2000/svg")
					path.pretix-widget-primary-color(d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z")
			.pretix-widget-lightbox-inner(v-if="store.overlay.lightbox")
				form.pretix-widget-lightbox-close(method="dialog")
					button(:aria-label="STRINGS.close", autofocus)
						svg(:alt="STRINGS.close", height="16", viewBox="0 0 512 512", width="16", xmlns="http://www.w3.org/2000/svg")
							path(fill="#fff", d="M437.5,386.6L306.9,256l130.6-130.6c14.1-14.1,14.1-36.8,0-50.9c-14.1-14.1-36.8-14.1-50.9,0L256,205.1L125.4,74.5 c-14.1-14.1-36.8-14.1-50.9,0c-14.1,14.1-14.1,36.8,0,50.9L205.1,256L74.5,386.6c-14.1,14.1-14.1,36.8,0,50.9 c14.1,14.1,36.8,14.1,50.9,0L256,306.9l130.6,130.6c14.1,14.1,36.8,14.1,50.9,0C451.5,423.4,451.5,400.6,437.5,386.6z")
				figure.pretix-widget-lightbox-image
					img(
						ref="lightboxImage",
						:src="store.overlay.lightbox.image",
						:alt="store.overlay.lightbox.description",
						crossorigin,
						@load="lightboxLoaded"
					)
					figcaption(v-if="store.overlay.lightbox.description") {{ store.overlay.lightbox.description }}
</template>

<style lang="sass">
</style>
