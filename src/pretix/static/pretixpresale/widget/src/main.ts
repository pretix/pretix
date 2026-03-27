import { createApp, nextTick, type App } from 'vue'
import { createWidgetInstance } from '~/widget'
import { createButtonInstance } from '~/button'
import { createWidgetStore, StoreKey } from '~/sharedStore'
import ButtonComponent from '~/components/Button.vue'
import { docReady, makeid } from '~/utils'
import type { WidgetData } from '~/types'

declare global {
	interface Window {
		PretixWidget: PretixWidgetAPI
		pretixWidgetCallback?: () => void
	}
}

interface PretixWidgetAPI {
	build_widgets: boolean
	widget_data: WidgetData
	buildWidgets: () => void
	open: (
		targetUrl: string,
		voucher?: string | null,
		subevent?: string | number | null,
		items?: { item: string; count: string }[],
		widgetData?: Record<string, string>,
		skipSslCheck?: boolean,
		disableIframe?: boolean
	) => void
	addLoadListener: (callback: () => void) => void
	addCloseListener: (callback: () => void) => void
	_loaded: Array<() => void>
	_closed: Array<() => void>
}

const widgetlist: App[] = []
const buttonlist: App[] = []

window.PretixWidget = {
	build_widgets: true,
	widget_data: { referer: location.href },
	// TODO move somewhere else and rename?
	_loaded: [],
	_closed: [],
	buildWidgets,
	open: openWidget,
	addLoadListener (f) { this._loaded.push(f) },
	addCloseListener (f) { this._closed.push(f) },
}

async function buildWidgets () {
	await docReady()
	const widgetElements = document.querySelectorAll('pretix-widget, div.pretix-widget-compat')
	for (const [i, el] of Array.from(widgetElements).entries()) {
		widgetlist.push(createWidgetInstance(el, el.id || `pretix-widget-${i}`))
	}
	const buttonElements = document.querySelectorAll('pretix-button, div.pretix-button-compat')
	for (const [i, el] of Array.from(buttonElements).entries()) {
		buttonlist.push(createButtonInstance(el, el.id || `pretix-button-${i}`))
	}
}

function openWidget (
	targetUrl: string,
	voucher?: string | null,
	subevent?: string | number | null,
	items?: { item: string; count: string }[],
	widgetData?: Record<string, string>,
	skipSslCheck?: boolean,
	disableIframe?: boolean
): void {
	if (!targetUrl.match(/\/$/)) {
		targetUrl += '/'
	}

	const allWidgetData: WidgetData = JSON.parse(JSON.stringify(window.PretixWidget.widget_data))
	if (widgetData) {
		Object.assign(allWidgetData, widgetData)
	}

	const root = document.createElement('div')
	document.body.appendChild(root)
	root.classList.add('pretix-widget-hidden')

	const store = createWidgetStore({
		targetUrl,
		voucher: voucher ?? null,
		subevent: subevent ?? null,
		skipSsl: skipSslCheck ?? false,
		disableIframe: disableIframe ?? false,
		widgetData: allWidgetData,
		htmlId: makeid(16),
		isButton: true,
		buttonItems: items ?? [],
		buttonText: '',
	})

	const app = createApp(ButtonComponent)
	app.provide(StoreKey, store)
	app.config.errorHandler = (error, _vm, info) => {
		console.error('[pretix-widget-open]', info, error)
	}
	app.mount(root)

	nextTick(() => {
		if (store.useIframe) {
			const form = root.querySelector('form') as HTMLFormElement
			if (form) {
				const formData = new FormData(form)
				store.buy(formData)
			}
		} else {
			const form = root.querySelector('form') as HTMLFormElement
			if (form) form.submit()
		}
	})
}

if (typeof window.pretixWidgetCallback !== 'undefined') {
	window.pretixWidgetCallback()
}

if (window.PretixWidget.build_widgets) {
	window.PretixWidget.buildWidgets()
}

// TODO debug exposes
