// Utility functions for the pretix widget

import { getFormat } from '~/i18n'

// Cookie utilities
export function setCookie (cname: string, cvalue: string, exdays: number): void {
	const d = new Date()
	d.setTime(d.getTime() + exdays * 24 * 60 * 60 * 1000)
	const expires = `expires=${d.toUTCString()}`
	document.cookie = `${cname}=${cvalue};${expires};path=/`
}

export function getCookie (name: string): string | null {
	const value = `; ${document.cookie}`
	const parts = value.split(`; ${name}=`)
	if (parts.length === 2) {
		return parts.pop()?.split(';').shift() || null
	}
	return null
}

// Number formatting
export function roundTo (n: number, digits = 0): number {
	const multiplicator = Math.pow(10, digits)
	n = parseFloat((n * multiplicator).toFixed(11))
	return Math.round(n) / multiplicator
}

// TODO use https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat instead?
export function floatformat (val: number | string, places = 2): string {
	if (typeof val === 'string') {
		val = parseFloat(val)
	}
	const parts = roundTo(val, places).toFixed(places).split('.')
	if (places === 0) {
		return parts[0]
	}
	const grouping = getFormat('NUMBER_GROUPING') as number
	const thousandSep = getFormat('THOUSAND_SEPARATOR') as string
	const decimalSep = getFormat('DECIMAL_SEPARATOR') as string
	parts[0] = parts[0].replace(
		new RegExp(`\\B(?=(\\d{${grouping}})+(?!\\d))`, 'g'),
		thousandSep
	)
	return `${parts[0]}${decimalSep}${parts[1]}`
}

export function autofloatformat (val: number | string, places = 2): string {
	const numVal = typeof val === 'string' ? parseFloat(val) : val
	if (numVal === roundTo(numVal, 0)) {
		places = 0
	}
	return floatformat(numVal, places)
}

// String/number utilities
export function padNumber (number: number, size = 2): string {
	let s = String(number)
	while (s.length < size) {
		s = `0${s}`
	}
	return s
}

export function getISOWeeks (year: number): number {
	const d = new Date(year, 0, 1)
	const isLeap = new Date(year, 1, 29).getMonth() === 1
	// Check for a Jan 1 that's a Thursday or a leap year that has a Wednesday Jan 1
	return d.getDay() === 4 || (isLeap && d.getDay() === 3) ? 53 : 52
}

export function makeid (length: number): string {
	let text = ''
	const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
	for (let i = 0; i < length; i++) {
		text += possible.charAt(Math.floor(Math.random() * possible.length))
	}
	return text
}

export function siteIsSecure (): boolean {
	return /https.*/.test(document.location.protocol)
}

// HTML utility
export function stripHTML (s: string): string {
	const div = document.createElement('div')
	div.innerHTML = s
	return div.textContent || div.innerText || ''
}

// docReady - DOM ready detection (returns a Promise)
export function docReady (): Promise<void> {
	if (document.readyState === 'complete' || document.readyState === 'interactive') {
		return Promise.resolve()
	}
	return new Promise(resolve => {
		document.addEventListener('DOMContentLoaded', () => resolve(), { once: true })
	})
}
