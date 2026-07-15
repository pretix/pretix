export function i18nstringLocalize(s: I18nString): string {
    if (typeof s === 'string') {
        return s
    }
    if (s === null) {
        return null
    }

    var locale = document.body.attributes['data-pretixlocale'].value
    var short_locale = locale.split('-')[0]
    if (locale in s)
        return s[locale]

    if (short_locale in s)
        return s[short_locale]

    for (const k of Object.keys(s)) {
        if (k.split('-')[0] === short_locale && s[k]) {
            return s[k]
        }
    }

    if (s['en'])
        return s['en']

    for (const k of Object.keys(s)) {
        if (s[k]) {
            return s[k]
        }
    }
}

