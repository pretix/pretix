import { ref, watch } from 'vue'

export const allProducts = ref(false)
export const limitProducts = ref<number[]>([])

function updateProducts () {
	allProducts.value = document.querySelector<HTMLInputElement>('#id_all_products')?.checked ?? false
	limitProducts.value = Array.from(document.querySelectorAll<HTMLInputElement>('input[name=limit_products]:checked')).map(el => parseInt(el.value))
}

// listen to change events for products
document.querySelectorAll('#id_all_products, input[name=limit_products]').forEach(el => el.addEventListener('change', updateProducts))
updateProducts()

export const rules = ref<any>({})

// grab rules from hidden input
const rulesInput = document.querySelector<HTMLInputElement>('#id_rules')
if (rulesInput?.value) {
	rules.value = JSON.parse(rulesInput.value)
}

// sync back to hidden input
watch(rules, (newVal) => {
	if (!rulesInput) return
	rulesInput.value = JSON.stringify(newVal)
}, { deep: true })

export const items = ref<any[]>([])

const itemsEl = document.querySelector('#items')
if (itemsEl?.textContent) {
	items.value = JSON.parse(itemsEl.textContent || '[]')

	function checkForInvalidIds (validProducts: Record<string, string>, validVariations: Record<string, string>, rule: any) {
		if (rule['and']) {
			for (const child of rule['and'])
				checkForInvalidIds(validProducts, validVariations, child)
		} else if (rule['or']) {
			for (const child of rule['or'])
				checkForInvalidIds(validProducts, validVariations, child)
		} else if (rule['inList'] && rule['inList'][0]['var'] === 'product') {
			for (const item of rule['inList'][1]['objectList']) {
				if (!validProducts[item['lookup'][1]])
					item['lookup'][2] = '[' + gettext('Error: Product not found!') + ']'
				else
					item['lookup'][2] = validProducts[item['lookup'][1]]
			}
		} else if (rule['inList'] && rule['inList'][0]['var'] === 'variation') {
			for (const item of rule['inList'][1]['objectList']) {
				if (!validVariations[item['lookup'][1]])
					item['lookup'][2] = '[' + gettext('Error: Variation not found!') + ']'
				else
					item['lookup'][2] = validVariations[item['lookup'][1]]
			}
		}
	}

	checkForInvalidIds(
		Object.fromEntries(items.value.map(p => [p.id, p.name])),
		Object.fromEntries(items.value.flatMap(p => p.variations?.map(v => [v.id, p.name + ' – ' + v.name]) ?? [])),
		rules.value
	)
}

export const productSelectURL = ref(document.querySelector('#product-select2')?.textContent)
export const variationSelectURL = ref(document.querySelector('#variations-select2')?.textContent)
export const gateSelectURL = ref(document.querySelector('#gate-select2')?.textContent)
