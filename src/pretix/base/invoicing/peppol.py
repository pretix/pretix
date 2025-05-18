import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_countries.fields import Country

from pretix.base.invoicing.transmission import (
    TransmissionType, transmission_types,
)


class PeppolIdValidator:
    regex_rules = {
        # Source: https://docs.peppol.eu/edelivery/codelists/old/v8.5/Peppol%20Code%20Lists%20-%20Participant%20identifier%20schemes%20v8.5.html
        "0002": "[0-9]{9}([0-9]{5})?",
        "0007": "[0-9]{10}",
        "0009": "[0-9]{14}",
        "0037": "(0037)?[0-9]{7}-?[0-9][0-9A-Z]{0,5}",
        "0060": "[0-9]{9}",
        "0088": "[0-9]{13}",
        "0096": "[0-9]{17}",
        "0097": "[0-9]{11,16}",
        "0106": "[0-9]{17}",
        "0130": ".*",
        "0135": ".*",
        "0142": ".*",
        "0151": "[0-9]{11}",
        "0183": "CHE[0-9]{9}",
        "0184": "DK[0-9]{8}([0-9]{2})?",
        "0188": ".*",
        "0190": "[0-9]{20}",
        "0191": "[1789][0-9]{7}",
        "0192": "[0-9]{9}",
        "0193": ".{4,50}",
        "0195": "[a-z]{2}[a-z]{3}([0-9]{8}|[0-9]{9}|[RST][0-9]{2}[a-z]{2}[0-9]{4})[0-9a-z]",
        "0196": "[0-9]{10}",
        "0198": "DK[0-9]{8}",
        "0199": "[A-Z0-9]{18}[0-9]{2}",
        "0020": "[0-9]{9}",
        "0201": "[0-9a-zA-Z]{6}",
        "0204": "[0-9]{2,12}(-[0-9A-Z]{0,30})?-[0-9]{2}",
        "0208": "0[0-9]{9}",
        "0209": ".*",
        "0210": "[A-Z0-9]+",
        "0211": "IT[0-9]{11}",
        "0212": "[0-9]{7}-[0-9]",
        "0213": "FI[0-9]{8}",
        "0205": "[A-Z0-9]+",
        "0221": "T[0-9]{13}",
        "0230": ".*",
        "9901": ".*",
        "9902": "[1-9][0-9]{7}",
        "9904": "DK[0-9]{8}",
        "9909": "NO[0-9]{9}MVA",
        "9910": "HU[0-9]{8}",
        "9912": "[A-Z]{2}[A-Z0-9]{,20}",
        "9913": ".*",
        "9914": "ATU[0-9]*",
        "9915": "[A-Z][A-Z0-9]*",
        "9916": ".*",
        "9917": "[0-9]{10}",
        "9918": "[A-Z]{2}[0-9]{2}[A-Z-0-9]{11,30}",
        "9919": "[A-Z][0-9]{3}[A-Z][0-9]{3}[A-Z]",
        "9920": ".*",
        "9921": ".*",
        "9922": ".*",
        "9923": ".*",
        "9924": ".*",
        "9925": ".*",
        "9926": ".*",
        "9927": ".*",
        "9928": ".*",
        "9929": ".*",
        "9930": ".*",
        "9931": ".*",
        "9932": ".*",
        "9933": ".*",
        "9934": ".*",
        "9935": ".*",
        "9936": ".*",
        "9937": ".*",
        "9938": ".*",
        "9939": ".*",
        "9940": ".*",
        "9941": ".*",
        "9942": ".*",
        "9943": ".*",
        "9944": ".*",
        "9945": ".*",
        "9946": ".*",
        "9947": ".*",
        "9948": ".*",
        "9949": ".*",
        "9950": ".*",
        "9951": ".*",
        "9952": ".*",
        "9953": ".*",
        "9954": ".*",
        "9956": "0[0-9]{9}",
        "9957": ".*",
        "9959": ".*",
    }

    def __call__(self, value):
        if ":" not in value:
            raise ValidationError(_("A PEPPOL participant ID always starts with a prefix, followed by a colon (:)."))

        prefix, second = value.split(":", 1)
        if prefix not in self.regex_rules:
            raise ValidationError(_("The PEPPOL participant ID prefix %(number)s is not known to our system. Please "
                                    "reach out to us if you are sure this ID is correct."), params={"number": prefix})

        if not re.match(self.regex_rules[prefix], second):
            raise ValidationError(_("The PEPPOL participant ID does not match the validation rules for the prefix "
                                    "%(number)s. Please reach out to us if you are sure this ID is correct."),
                                  params={"number": prefix})
        return value


@transmission_types.new()
class PeppolTransmissionType(TransmissionType):
    identifier = "peppol"
    verbose_name = "PEPPOL"

    def is_available(self, event, country: Country, is_business: bool):
        return is_business and super().is_available(event, country, is_business)

    @property
    def invoice_address_form_fields(self) -> dict:
        return {
            "transmission_peppol_participant_id": forms.CharField(
                label=_("PEPPOL participant ID"),
                validators=[
                    PeppolIdValidator(),
                ]
            ),
        }

    def invoice_address_form_fields_required(self, country: Country, is_business: bool):
        return {"transmission_peppol_participant_id"}
