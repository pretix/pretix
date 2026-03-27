
export function i18n_any(data) {
	if (!data) return null;
	const preferred = document.body.getAttribute("data-pretixlocale");
	if (data[preferred]) return data[preferred];
  return Object.values(data)[0];
}

function freezeRec(o) {
	return Object.freeze(Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v && Object.getPrototypeOf(v) === Object.prototype ? freezeRec(v) : v])))
}

export const QUESTION_TYPE = {
  NUMBER: "N",
  STRING: "S",
  TEXT: "T",
  BOOLEAN: "B",
  CHOICE: "C",
  CHOICE_MULTIPLE: "M",
  FILE: "F",
  DATE: "D",
  TIME: "H",
  DATETIME: "W",
  COUNTRYCODE: "CC",
  PHONENUMBER: "TEL",
};

const _ = x => x;

export const QUESTION_TYPE_LABEL = {
    NUMBER: _("Number"),
    STRING: _("Text (one line)"),
    TEXT: _("Multiline text"),
    BOOLEAN: _("Yes/No"),
    CHOICE: _("Choose one from a list"),
    CHOICE_MULTIPLE: _("Choose multiple from a list"),
    FILE: _("File upload"),
    DATE: _("Date"),
    TIME: _("Time"),
    DATETIME: _("Date and time"),
    COUNTRYCODE: _("Country code (ISO 3166-1 alpha-2)"),
    PHONENUMBER: _("Phone number"),
};

export const SYSTEM_DATAFIELDS = freezeRec({
		'attendee_name_parts': { label: _('Attendee name'), type: QUESTION_TYPE.STRING },
		'attendee_email': { label: _('Attendee email'), type: QUESTION_TYPE.STRING },
		'company': { label: _('Company'), type: QUESTION_TYPE.STRING },
		'street': { label: _('Street'), type: QUESTION_TYPE.STRING },
		'zipcode': { label: _('ZIP code'), type: QUESTION_TYPE.STRING },
		'city': { label: _('City'), type: QUESTION_TYPE.STRING },
		'country': { label: _('Country'), type: QUESTION_TYPE.COUNTRYCODE },
});
