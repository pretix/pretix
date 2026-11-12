export function dateTimeFormat(d: string, options?: Record<string, string>): string {
    const locale = document.body.attributes['data-pretixlocale'].value
    return new Intl.DateTimeFormat(locale, options).format(new Date(d))
}