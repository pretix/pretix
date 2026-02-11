import { createApp, type App } from 'vue'
import ButtonComponent from '~/components/Button.vue'
import { createWidgetStore, StoreKey } from '~/sharedStore'
import { makeid } from '~/utils'
import type { WidgetData } from '~/types'

export function createButtonInstance (element: Element, htmlId?: string): App {
	let targetUrl = element.attributes.event.value
	if (!targetUrl.match(/\/$/)) {
		targetUrl += '/'
	}

	const widgetData: WidgetData = JSON.parse(JSON.stringify(window.PretixWidget.widget_data))

	for (const attr of Array.from(element.attributes)) {
		if (attr.name.match(/^data-.*$/)) {
			widgetData[attr.name.replace(/^data-/, '')] = attr.value
		}
	}

	const rawItems = element.attributes.items?.value || ''

	// Parse items string (format: "item_1=2,item_3=1")
	const buttonItems: { item: string; count: string }[] = []
	for (const itemStr of rawItems.split(',')) {
		if (itemStr.includes('=')) {
			const [item, count] = itemStr.split('=')
			buttonItems.push({ item, count })
		}
	}

	const store = createWidgetStore({
		targetUrl,
		voucher: element.attributes.voucher?.value || null,
		subevent: element.attributes.subevent?.value || null,
		skipSsl: 'skip-ssl-check' in element.attributes,
		disableIframe: 'disable-iframe' in element.attributes,
		widgetData,
		htmlId: htmlId || element.id || makeid(16),
		isButton: true,
		buttonItems,
		buttonText: element.innerHTML
	})

	const observer = new MutationObserver((mutationList) => {
		for (const mutation of mutationList) {
			if (mutation.type === 'attributes' && mutation.attributeName?.startsWith('data-')) {
				const attrName = mutation.attributeName.substring(5)
				const attrValue = (mutation.target as Element).getAttribute(mutation.attributeName)
				if (attrValue !== null) {
					store.widgetData[attrName] = attrValue
				}
			}
		}
	})

	// TODO I don't think we need this anymore in vue3
	// if (element.tagName !== 'pretix-button') {
	// 	element.innerHTML = '<pretix-button>' + element.innerHTML + '</pretix-button>'
	// 	// Vue does not replace the container, so watch container as well
	// 	observer.observe(element, observerOptions)
	// }

	const app = createApp(ButtonComponent)
	app.provide(StoreKey, store)
	app.config.errorHandler = (error, _vm, info) => {
		console.error('[pretix-button]', info, error)
	}
	app.mount(element)
	observer.observe(element, { attributes: true })

	return app
}
