function i18nstring_localize(o) {
    var locale = document.body.attributes['data-pretixlocale'].value
    var short_locale = locale.split('-')[0]
    if (o[locale])
        return o[locale]

    if (o[short_locale])
        return o[short_locale]

    for (k of Object.keys(o)) {
        if (k.split('-')[0] === short_locale && o[k]) {
            return o[k]
        }
    }

    if (o['en'])
        return o['en']

    for (k of Object.keys(o)) {
        if (o[k]) {
            return o[k]
        }
    }
}

