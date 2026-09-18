/* global gettext, pgettext */

export function i18n_any (data) {
	if (!data) return null
	const preferred = document.body.getAttribute('data-pretixlocale')
	if (data[preferred]) return data[preferred]
	return Object.values(data)[0]
}

function freezeRec (o) {
	return Object.freeze(Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v && Object.getPrototypeOf(v) === Object.prototype ? freezeRec(v) : v])))
}

export function localeComp (fn) {
	return function (a, b) {
		return fn(a).localeCompare(fn(b))
	}
}
export function numericComp (fn) {
	return function (a, b) {
		return fn(a) - fn(b)
	}
}
export function pick (key) {
	return function (obj) {
		return obj[key]
	}
}
export function sort (array, ...orderBy) {
	array.sort(function (a, b) {
		for (let comp of orderBy) {
			const result = comp(a, b)
			if (result !== 0) {
				return result
			}
		}
		return 0
	})
}
export function *groupBy (array, key) {
	let lastKey, lastArray
	for (const x of array) {
		const k = key(x)
		if (lastKey !== k || !lastArray) {
			if (lastArray) {
				yield [lastKey, lastArray]
			}
			lastKey = k; lastArray = [x]
		} else {
			lastArray.push(x)
		}
	}
	if (lastArray) {
		yield [lastKey, lastArray]
	}
}

export function fromJsonScript (id) {
	return JSON.parse(document.getElementById(id).textContent)
}

export const QUESTION_TYPE = Object.fromEntries(fromJsonScript('question_type_choices').map(([name, value, label]) => [name, value]))
export const QUESTION_TYPE_LABEL = Object.fromEntries(fromJsonScript('question_type_choices').map(([name, value, label]) => [name, i18n_any(label)]))

export const SYSTEM_DATAFIELDS = freezeRec(Object.fromEntries(fromJsonScript('system_question_choices').map(([name, value, label]) => [
	value, { id: value, question: label, type: value === 'country' ? QUESTION_TYPE.COUNTRYCODE : QUESTION_TYPE.STRING }
])))

export const QUESTIONNAIRE_TYPE = Object.fromEntries(fromJsonScript('questionnaire_type_choices').map(([name, value, label]) => [name, value]))
export const QUESTIONNAIRE_TYPE_LABEL = Object.fromEntries(fromJsonScript('questionnaire_type_choices').map(([name, value, label]) => [name, i18n_any(label)]))
