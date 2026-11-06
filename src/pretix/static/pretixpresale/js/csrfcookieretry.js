document.addEventListener('DOMContentLoaded', () => {
	const COOKIE_NAME = '__Host-pretix_csrftoken'
	const RELOAD_FLAG = 'csrfReloadPerformed'

	const CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

	// reimplementation of CSRFMiddlewares _unmask_cipher_token()
	const unmask = (token) => {
		if (!token || token.length !== 64) return token || null
		let secret = ''
		for (let i = 0; i < 32; i++) {
			const m = CHARS.indexOf(token[i])
			const c = CHARS.indexOf(token[32 + i])
			if (m < 0 || c < 0) return null
			secret += CHARS[(c - m + CHARS.length) % CHARS.length]
		}
		return secret
	}

	const cookie = document.cookie
		.split('; ')
		.find((c) => c.startsWith(COOKIE_NAME + '='))
	const cookieSecret = cookie ? unmask(cookie.slice(COOKIE_NAME.length + 1)) : null

	const field = document.querySelector('input[name="csrfmiddlewaretoken"]')
	const pageSecret = field ? unmask(field.value) : null
	const cookiesNotMatching = (pageSecret !== null && pageSecret !== cookieSecret)

	const broken = !cookieSecret || cookiesNotMatching

	if (broken && !sessionStorage.getItem(RELOAD_FLAG)) {
		sessionStorage.setItem(RELOAD_FLAG, '1')
		location.href = location.href
	} else if (!broken && sessionStorage.getItem(RELOAD_FLAG)) {
		sessionStorage.removeItem(RELOAD_FLAG)
	}
})
