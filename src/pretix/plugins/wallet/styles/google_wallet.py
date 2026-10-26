import enum
import time
from datetime import datetime
from typing import Iterable

from google.auth import crypt, jwt
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from pretix.plugins.wallet.i18n import (
    MaybeTranslatedString, localizable_to_dict,
)


class ReviewStatus(enum.StrEnum):
    APPROVED = "APPROVED"
    DRAFT = "DRAFT"
    REJECTED = "REJECTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    REVIEW_STATUS_UNSPECIFIED = "REVIEW_STATUS_UNSPECIFIED"


class ConfirmationCodeLabel(enum.StrEnum):
    CONFIRMATION_CODE = "CONFIRMATION_CODE"
    CONFIRMATION_NUMBER = "CONFIRMATION_NUMBER"
    ORDER_NUMBER = "ORDER_NUMBER"
    RESERVATION_NUMBER = "RESERVATION_NUMBER"


class AnimationType(enum.StrEnum):
    FOIL_SHIMMER = "FOIL_SHIMMER"


class DoorsOpenLabel(enum.StrEnum):
    DOORS_OPEN = "DOORS_OPEN"
    GATES_OPEN = "GATES_OPEN"


class State(enum.StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    INACTIVE = "INACTIVE"


class BarcodeType(enum.StrEnum):
    AZTEC = "AZTEC"
    CODE_39 = "CODE_39"
    CODE_128 = "CODE_128"
    CODABAR = "CODABAR"
    DATA_MATRIX = "DATA_MATRIX"
    EAN_8 = "EAN_8"
    EAN_13 = "EAN_13"
    EAN13 = "EAN13"
    ITF_14 = "ITF_14"
    PDF_417 = "PDF_417"
    PDF417 = "PDF417"
    QR_CODE = "QR_CODE"
    UPC_A = "UPC_A"
    TEXT_ONLY = "TEXT_ONLY"


class Resource(enum.StrEnum):
    EVENT_TICKET_CLASS = "eventTicketClass"
    EVENT_TICKET_OBJECT = "eventTicketObject"


def item(field):
    return {"firstValue": {"fields": [{"fieldPath": field}]}}


def card_row_template_info(fields: Iterable[str]):
    items = [item(field) for field in fields]
    if len(items) == 3:
        return {
            "threeItems": {
                "startItem": items[0],
                "middleItem": items[1],
                "endItem": items[2],
            }
        }
    elif len(items) == 2:
        return {
            "twoItems": {
                "startItem": items[0],
                "endItem": items[1],
            }
        }
    else:
        return {
            "oneItem": {
                "startItem": items[0],
            }
        }


def localized_string(
    string: MaybeTranslatedString, locales: set[str], default_locale: str
):
    if isinstance(string, str):
        return {
            "defaultValue": {
                "language": default_locale,
                "value": string,
            }
        }
    else:
        string_dict = localizable_to_dict(string, locales)
        default_string = string_dict.pop(default_locale)

        return {
            "defaultValue": {
                "language": default_locale,
                "value": default_string,
            },
            "translatedValues": [
                {"language": key, "value": value} for key, value in string_dict.items()
            ],
        }


def localized_uri(
    uri: str, description: MaybeTranslatedString, locales: set[str], default_locale: str
):
    return {
        "uri": uri,
        "localizedDescription": localized_string(description, locales, default_locale),
    }


class Image(dict):
    def __init__(
        self,
        uri: str,
        content_description: MaybeTranslatedString,
        locales: set[str],
        default_locale: str,
    ):
        self["uri"] = uri
        self["contentDescription"] = localized_string(
            content_description, locales, default_locale
        )


class BaseGoogleWalletObject:
    resource: Resource
    id: str
    data: dict

    locales: set[str]
    default_locale: str

    def _localized_string(self, string: MaybeTranslatedString):
        return localized_string(string, self.locales, self.default_locale)

    def _localized_uri(
        self,
        uri: str,
        description: MaybeTranslatedString,
    ):
        return localized_uri(uri, description, self.locales, self.default_locale)

    def _image(self, uri: str, content_description: MaybeTranslatedString):
        return {
            "sourceUri": {"uri": uri},
            "contentDescription": self._localized_string(content_description),
        }

    def serialize(self, mini=True):
        if mini:
            return {"id": self.id}
        else:
            return self.data


class EventTicketClass(BaseGoogleWalletObject):
    resource = Resource.EVENT_TICKET_CLASS

    def __init__(
        self,
        issuer_name: str,
        class_id: str,
        event_name: MaybeTranslatedString,
        locales: set[str],
        default_locale: str,
    ):
        self.id = class_id
        self.default_locale = default_locale
        self.locales = locales
        self.data = {
            "id": class_id,
            "issuerName": issuer_name,
            "eventName": localized_string(
                event_name, self.locales, self.default_locale
            ),
            "reviewStatus": ReviewStatus.UNDER_REVIEW,
        }

    def homepage_uri(
        self,
        uri: str,
        description: MaybeTranslatedString,
    ):
        self.data["homepageUri"] = self._localized_uri(uri, description)

    def country_code(self, code: str):
        self.data["countryCode"] = code

    def hero_image(self, uri: str, content_description: MaybeTranslatedString):
        self.data["heroImage"] = self._image(uri, content_description)

    def logo(self, uri: str, content_description: MaybeTranslatedString):
        self.data["logo"] = self._image(uri, content_description)

    def wide_logo(self, uri: str, content_description: MaybeTranslatedString):
        self.data["wideLogo"] = self._image(uri, content_description)

    def hex_background_color(self, hex_background_color: str):
        self.data["hexBackgroundColor"] = hex_background_color

    def confirmation_code_label(self, label: ConfirmationCodeLabel):
        self.data["confirmationCodeLabel"] = label

    def venue(self, name: MaybeTranslatedString, address: MaybeTranslatedString):
        self.data["venue"] = {
            "name": self._localized_string(name),
            "address": self._localized_string(address),
        }

    def security_animation(self, security_animation: AnimationType):
        self.data["securityAnimation"] = security_animation

    def doors_open(
        self,
        doors_open: str,
        doors_open_label: None | DoorsOpenLabel | MaybeTranslatedString = None,
    ):
        self.data.setdefault("dateTime", {})
        self.data["dateTime"]["doorsOpen"] = doors_open

        if doors_open_label and isinstance(doors_open_label, DoorsOpenLabel):
            self.data["dateTime"]["doorsOpenLabel"] = doors_open_label
        elif doors_open_label:
            self.data["dateTime"]["customDoorsOpenLabel"] = self._localized_string(
                doors_open_label
            )

    def start(self, start):
        self.data.setdefault("dateTime", {})
        self.data["dateTime"]["start"] = start

    def end(self, end):
        self.data.setdefault("dateTime", {})
        self.data["dateTime"]["end"] = end

    def callback_url(self, callback_url: str):
        self.data["callbackOptions"] = {"url": callback_url}

    def card_template_override(self, overrides: list[list[str]]):
        self.data.setdefault("classTemplateInfo", {})
        self.data["classTemplateInfo"].setdefault("cardTemplateOverride", {})
        self.data["classTemplateInfo"]["cardTemplateOverride"][
            "cardRowTemplateInfos"
        ] = [card_row_template_info(x) for x in overrides]

    def details_item_infos(self, fields: list[str]):
        self.data.setdefault("classTemplateInfo", {})
        self.data["classTemplateInfo"].setdefault("detailsTemplateOverride", {})
        self.data["classTemplateInfo"]["detailsTemplateOverride"][
            "detailsItemInfos"
        ] = [{"item": item(field)} for field in fields]

    def add_text_module(
        self, id: str, header: MaybeTranslatedString, body: MaybeTranslatedString
    ):
        self.data.setdefault("textModulesData", [])
        self.data["textModulesData"].append(
            {
                "id": id,
                "localizedHeader": self._localized_string(header),
                "localizedBody": self._localized_string(body),
            }
        )


class EventTicketObject(BaseGoogleWalletObject):
    resource = Resource.EVENT_TICKET_OBJECT

    def __init__(
        self,
        object_id: str,
        class_id: str,
        state: State,
        locales: set[str],
        default_locale: str,
    ):
        self.id = object_id
        self.locales = locales
        self.default_locale = default_locale

        self.data = {
            "id": object_id,
            "classId": class_id,
            "state": state,
        }

    def barcode(
        self,
        value: str,
        alternate_text: str | None = None,
        type: BarcodeType = BarcodeType.QR_CODE,
    ):
        self.data["barcode"] = {
            "type": type,
            "value": value,
        }
        if alternate_text:
            self.data["barcode"]["alternateText"] = alternate_text

    def reservation_info(self, confirmation_code: str):
        self.data["reservationInfo"] = {
            "confirmationCode": confirmation_code,
        }

    def ticket_number(self, ticket_number: str):
        self.data["ticket_number"] = ticket_number

    def valid_time_interval(self, start: datetime | None, end: datetime | None):
        self.data.setdefault("validTimeInterval", {})
        if start:
            self.data["validTimeInterval"]["start"] = {"date": start.isoformat()}
        if end:
            self.data["validTimeInterval"]["end"] = {"date": end.isoformat()}

    def ticket_type(self, ticket_type: MaybeTranslatedString):
        self.data["ticketType"] = self._localized_string(ticket_type)

    def ticket_holder_name(self, name):
        self.data["ticketHolderName"] = name

    def seat(self, seat):
        self.data.setdefault("seatInfo", {})
        self.data["seatInfo"]["seat"] = self._localized_string(seat)

    def row(self, row):
        self.data.setdefault("seatInfo", {})
        self.data["seatInfo"]["row"] = self._localized_string(row)

    def section(self, section):
        self.data.setdefault("seatInfo", {})
        self.data["seatInfo"]["section"] = self._localized_string(section)

    def add_text_module(
        self, id: str, header: MaybeTranslatedString, body: MaybeTranslatedString
    ):
        self.data.setdefault("textModulesData", [])
        self.data["textModulesData"].append(
            {
                "id": id,
                "localizedHeader": self._localized_string(header),
                "localizedBody": self._localized_string(body),
            }
        )


class ButtonJWT(dict):
    def __init__(
        self,
        issuer,
        origins,
        payload: dict[str, list[BaseGoogleWalletObject]],
        precreated=True,
    ):
        serialized_payload = {}
        for k, v in payload.items():
            serialized_payload[k] = [x.serialize(mini=precreated) for x in v]

        self.payload = serialized_payload
        self.issuer = issuer
        self.origins = origins

    def serialize(self):
        return {
            "iss": self.issuer,
            "aud": "google",
            "typ": "savetowallet",
            "iat": int(time.time()),
            "payload": self.payload,
            "origins": self.origins,
        }


class Comms:
    def __init__(self, service_account_info: dict):
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/wallet_object.issuer"],
        )

        self._session = AuthorizedSession(credentials)
        self._signer = crypt.RSASigner.from_service_account_info(service_account_info)
        self.client_email = service_account_info.get("client_email")

    def get_item(self, resource: Resource, resource_id: str):
        result = self._session.get(
            f"https://walletobjects.googleapis.com/walletobjects/v1/{resource}/{resource_id}"
        )

        if result.status_code == 200:
            return result.json()
        elif result.status_code == 404:
            return False

    def put_item(self, resource: Resource, resource_id: str, payload: dict):
        item = self.get_item(resource, payload["id"])
        if item is None:
            raise Exception("API Error")
        elif not item:
            result = self._session.post(
                f"https://walletobjects.googleapis.com/walletobjects/v1/{resource}?strict=true",
                json=payload,
            )
        else:
            result = self._session.put(
                f"https://walletobjects.googleapis.com/walletobjects/v1/{resource}/{payload['id']}?strict=true",
                json=payload,
            )

        print(result.text)
        result.raise_for_status()

        return result.json()

    def sign_jwt(self, payload):
        encoded = jwt.encode(self._signer, payload)
        if not encoded:
            return False

        return encoded.decode("utf-8")
