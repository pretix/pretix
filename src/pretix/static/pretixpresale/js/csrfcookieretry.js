document.addEventListener('DOMContentLoaded', () => {
	const COOKIE_NAME = '__Host-pretix_csrftoken'
	const RELOAD_FLAG = 'csrfReloadPerformed'
	const REASON_PARAM = 'csrf_reload'
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

	const url = new URL(location.href)
	// remove reason after reload to avoid re-reports
	if (url.searchParams.has(REASON_PARAM)) {
		url.searchParams.delete(REASON_PARAM)
		history.replaceState(history.state, '', url)
	}

	const readCookieSecrets = () => document.cookie
		.split('; ')
		.filter((c) => c.startsWith(COOKIE_NAME + '='))
		.map((c) => unmask(c.slice(COOKIE_NAME.length + 1)))

	// a deletion only hits the variant whose attributes it matches
	const EXPIRE = `${COOKIE_NAME}=; Path=/; Secure; Max-Age=0`
	const deleteUnpartitioned = () => {
		document.cookie = EXPIRE
	}
	const deletePartitioned = () => {
		document.cookie = `${EXPIRE}; Partitioned`
	}

	const field = document.querySelector('input[name="csrfmiddlewaretoken"]')
	const pageSecret = field ? unmask(field.value) : null
	
	// bail if there is no pageSecret
	if (!pageSecret) return

	const check = (secrets) => {
		if (secrets.length === 0) return 'no_cookie'
		if (secrets.length > 1) return 'duplicate_cookie'
		if (!secrets[0]) return 'invalid_cookie'
		if (pageSecret !== null && pageSecret !== secrets[0]) return 'mismatch'
		return null
	}

	let cookieSecrets = readCookieSecrets()
	let reason = check(cookieSecrets)
	if (reason === 'duplicate_cookie') {
		// drop the unpartitioned cookie, keep the partitioned one, maybe this fixes all issues
		deleteUnpartitioned()
		cookieSecrets = readCookieSecrets()
		if (check(cookieSecrets)) {
			reason = 'duplicate_cookie'
		} else {
			reason = null
		}
	}

	if (reason && !sessionStorage.getItem(RELOAD_FLAG)) {
		sessionStorage.setItem(RELOAD_FLAG, '1')
		deleteUnpartitioned()
		deletePartitioned()
		url.searchParams.set(REASON_PARAM, reason)
		location.href = url.href
	} else if (!reason && sessionStorage.getItem(RELOAD_FLAG)) {
		sessionStorage.removeItem(RELOAD_FLAG)
	}
})
