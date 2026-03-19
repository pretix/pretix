
export function i18n_any(data) {
  return Object.values(data)[0];
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
