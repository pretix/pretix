import { createApp, type App } from 'vue'
import WidgetComponent from '~/components/Widget.vue'
import { createWidgetStore, StoreKey } from '~/sharedStore'
import { makeid } from '~/utils'
import type { WidgetData } from '~/types'

export function createWidgetInstance (element: Element, htmlId?: string): App {
	let targetUrl = element.attributes.event.value
	if (!targetUrl.match(/\/$/)) {
		targetUrl += '/'
	}

	const displayEventInfoAttr = element.attributes['display-event-info']?.value
	// null means "auto" (as before), everything other than "false" is true
	const displayEventInfo: boolean | null
		= 'display-event-info' in element.attributes && displayEventInfoAttr !== 'auto' ? displayEventInfoAttr !== 'false' : null

	const widgetData: WidgetData = JSON.parse(JSON.stringify(window.PretixWidget.widget_data))
	for (const attr of Array.from(element.attributes)) {
		if (attr.name.match(/^data-.*$/)) {
			widgetData[attr.name.replace(/^data-/, '')] = attr.value
		}
	}

	const store = createWidgetStore({
		targetUrl,
		voucher: element.attributes.voucher?.value || null,
		subevent: element.attributes.subevent?.value || null,
		listType: element.attributes['list-type']?.value || element.attributes.style?.value || null,
		skipSsl: 'skip-ssl-check' in element.attributes,
		disableIframe: 'disable-iframe' in element.attributes,
		disableVouchers: 'disable-vouchers' in element.attributes,
		disableFilters: 'disable-filters' in element.attributes,
		displayEventInfo,
		filter: element.attributes.filter?.value || null,
		items: element.attributes.items?.value || null,
		categories: element.attributes.categories?.value || null,
		variations: element.attributes.variations?.value || null,
		widgetData,
		htmlId: htmlId || element.id || makeid(16),
	})

	const observer = new MutationObserver((mutationList) => {
		for (const mutation of mutationList) {
			if (mutation.type === 'attributes' && mutation.attributeName?.startsWith('data-')) {
				const attrName = mutation.attributeName.substring(5)
				const attrValue = (mutation.target as Element).getAttribute(mutation.attributeName)
				store.widgetData[attrName] = attrValue
			}
		}
	})

	// TODO I don't think we need this anymore in vue3
	// if (element.tagName !== 'pretix-widget') {
	// 	element.innerHTML = '<pretix-widget></pretix-widget>'
	// 	// we need to watch the container as well as the replaced root-node (see mounted())
	// 	observer.observe(element, observerOptions)
	// }

	const app = createApp(WidgetComponent)
	app.provide(StoreKey, store)
	app.config.errorHandler = (error, _vm, info) => {
		console.error('[pretix-widget]', info, error)
	}
	app.mount(element)
	observer.observe(element, { attributes: true })

	return app
}
