import json

from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver

from pretix.base.models import Invoice, OrderPayment

from ..exporter import BaseExporter
from ..signals import register_data_exporters


class DekodiNREIExporter(BaseExporter):
    identifier = 'dekodi_nrei'
    verbose_name = 'dekodi NREI (JSON)'
    # Specification: http://manuals.dekodi.de/nexuspub/schnittstellenbuch/

    def _encode_invoice(self, invoice: Invoice):
        hdr = {
            'APmtA': None,
            'APmtAEUR': None,
            'C': str(invoice.invoice_to_country),
            'CA': None,
            'CAEUR': None,
            'CC': self.event.currency,
            'CGrp': None,
            'CID': None,
            'City': invoice.invoice_to_city,
            'CN': invoice.invoice_to_company,
            'CNo': None,
            'CoDA': None,
            'CoDAEUR': None,
            'DL': None,
            'DIC': None,  # Event-land?
            'DICt': None,
            'DIDt': invoice.order.datetime.isoformat().replace('Z', '+00:00'),
            'DIZ': None,
            'DN': None,
            'DT': '30' if invoice.is_cancellation else '10',
            'EbNm': None,
            'EbPmtID': Nine,
            'EM': invoice.order.email,
            'FamN': invoice.invoice_to_name,  # todo: split? should be last name
            'FCExR': None,
            'FN': invoice.invoice_to_name,  # todo: split? should be first name
            'FS': None,
            'GwA': None,
            'GwAEUR': None,
            'IDt': invoice.date.isoformat() + 'T08:00:00+01:00',
            'INo': invoice.full_invoice_no,
            'IsNet': invoice.reverse_charge,
            'IsPf': False,
            'IT': None,
            'KlnId': None,
            'ODt': invoice.order.datetime.isoformat().replace('Z', '+00:00'),
            'OID': invoice.order.code,
            'Pb': None,
            'PL': None,
            'PmDt': None,  # todo: payment date?
            'PPEm': None,  # todo: fill,
            'PvrINo': invoice.refers.full_invoice_no if invoice.refers else None,
            'PrvOID': None,
            'Rmrks': None,
            'ShA': None,
            'ShAEUR': None,
            'ShDt': None,
            'ShGrp': None,
            'SID': self.event.slug,
            'SN': str(self.event),
            'SSID': None,
            'SSINo': None,
            'SSN': None,
            'SSOID': None,
            'Str': invoice.invoice_to_street,
            'TGrossA': gross_total,  # TODO,
            'TGrossAEUR': None,
            'TNetA': net_total,   # TODO,
            'TNetAEUR': None,
            'TNo': None,
            'TT': None,
            'TVatA': vat_total,  # todo
            'VatDp': False,
            'VatID': invoice.invoice_to_vat_id or None,
            'Zip': invoice.invoice_to_zipcode

        }
        positions = []
        for l in invoice.lines.all():
            positions.append({
                'ABcd': None,
                'ADes': l.description,
                'ANetA': round(float(l.net_value), 2),
                'ANetAEUR': None,
                'ANo': None,  # TODO: needs to be there!
                'ANo1': None,
                'ANo2': None,
                'ANoEx': None,
                'ANoM': None,
                'AQ': -1 if invoice.is_cancellation else 1,
                'ASku': None,
                'AST': 0,
                'ATm': None,
                'ATT': None,
                'AU': None,
                'AVatP': round(float(l.tax_rate), 2),
                'AWgt': None,
                'DiC': None,
                'DiCeID': None,
                'DICeN': None,
                'DiZ': None,
                'DIDt': (l.subevent or invoice.order.event).date_from.isoformat().replace('Z', '+00:00'),
                'OC': None,
                'PosGrossA': round(float((-1 if invoice.is_cancellation else 1) * l.gross_value), 2),
                'PosGrossAEUR': None,
                'PosNetA': round(float((-1 if invoice.is_cancellation else 1) * l.net_value), 2),
                'PosNetAEUR': None,
            })
        payments = []
        for p in invoice.order.payments.filter(
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_PENDING,
                       OrderPayment.PAYMENT_STATE_STARTED, OrderPayment.PAYMENT_STATE_REFUNDED)
        ):
            if p.provider == 'paypal':
                payments.append({
                    'PTID': '1',
                    'PTN': 'PayPal',
                    'PTNo1': None,  # TODO: transaktionsid
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': None,
                    'PTNo5': None,
                    'PTNo6': None,
                    'PTNo7': None,
                    'PTNo8': None,
                    'PTNo9': None,
                    'PTNo10': None,
                    'PTNo11': None,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': None,
                    'PTNo15': None,
                })
            elif p.provider == 'banktransfer':
                payments.append({
                    'PTID': '4',
                    'PTN': 'Vorkasse',
                    'PTNo1': None,  # TODO: transaktionsid
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': None,
                    'PTNo5': None,
                    'PTNo6': None,
                    'PTNo7': None,
                    'PTNo8': None,
                    'PTNo9': None,
                    'PTNo10': None,
                    'PTNo11': None,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': None,
                    'PTNo15': None,
                })
            elif p.provider == 'sepadebit':
                payments.append({
                    'PTID': '5',
                    'PTN': 'Lastschrift',
                    'PTNo1': None,  # TODO: transaktionsid
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': None,
                    'PTNo5': None,
                    'PTNo6': None,
                    'PTNo7': None,
                    'PTNo8': None,
                    'PTNo9': None,
                    'PTNo10': None,
                    'PTNo11': None,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': None,
                    'PTNo15': None,
                })
            elif p.provider.startswith('stripe'):
                payments.append({
                    'PTID': '81',
                    'PTN': 'Stripe',
                    'PTNo1': None,  # TODO: transaktionsid
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': None,
                    'PTNo5': None,
                    'PTNo6': None,
                    'PTNo7': None,
                    'PTNo8': None,
                    'PTNo9': None,
                    'PTNo10': None,
                    'PTNo11': None,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': None,
                    'PTNo15': None,
                })
        return {
            'IsValid': True,
            'Hdr': hdr,
            'InvcPstns': positions,
            'PmIs': payments,
            'ValidationMessage': ''
        }

    def render(self, form_data):
        jo = {
            'Format': 'NREI',
            'Version': '18.10.2',
            'SourceSystem': 'pretix',
            'Data': [
                self._encode_invoice(i) for i in self.event.invoices.select_related('order').prefetch_related('lines', 'lines__subevent')
            ]
        }
        return '{}_nrei.json'.format(self.event.slug), 'application/json', json.dumps(jo, cls=DjangoJSONEncoder)


@receiver(register_data_exporters, dispatch_uid="exporter_dekodi_nrei")
def register_dekodi_export(sender, **kwargs):
    return DekodiNREIExporter
