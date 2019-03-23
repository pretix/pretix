import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver
from django.utils.translation import ugettext

from pretix.base.i18n import language
from pretix.base.models import Invoice, OrderPayment

from ..exporter import BaseExporter
from ..signals import register_data_exporters


class DekodiNREIExporter(BaseExporter):
    identifier = 'dekodi_nrei'
    verbose_name = 'dekodi NREI (JSON)'
    # Specification: http://manuals.dekodi.de/nexuspub/schnittstellenbuch/

    def _encode_invoice(self, invoice: Invoice):
        p_last = invoice.order.payments.filter(state=[OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED]).last()
        gross_total = Decimal('0.00')
        net_total = Decimal('0.00')

        positions = []
        for l in invoice.lines.all():
            positions.append({
                'ABcd': None,
                'ADes': l.description.replace("<br />", "\n"),
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
            gross_total += l.gross_value
            net_total += l.net_value

        payments = []
        paypal_email = None
        for p in invoice.order.payments.filter(
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_PENDING,
                       OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_REFUNDED)
        ):
            if p.provider == 'paypal':
                paypal_email = p.info_data.get('payer', {}).get('payer_info', {}).get('email')
                payments.append({
                    'PTID': '1',
                    'PTN': 'PayPal',
                    'PTNo1': p.info_data.get('id'),
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': None,
                    'PTNo5': None,
                    'PTNo6': None,
                    'PTNo7': round(float(p.amount), 2),
                    'PTNo8': str(self.event.currency),
                    'PTNo9': None,
                    'PTNo10': None,
                    'PTNo11': paypal_email,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': None,
                    'PTNo15': p.full_id,
                })
            elif p.provider == 'banktransfer':
                payments.append({
                    'PTID': '4',
                    'PTN': 'Vorkasse',
                    'PTNo1': None,
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': p.info_data.get('reference') or p.payment_provider._code(invoice.order),
                    'PTNo5': None,
                    'PTNo6': None,
                    'PTNo7': round(float(p.amount), 2),
                    'PTNo8': str(self.event.currency),
                    'PTNo9': None,
                    'PTNo10': p.info_data.get('payer'),
                    'PTNo11': None,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': p.info_data.get('date'),
                    'PTNo15': p.full_id,
                })
            elif p.provider == 'sepadebit':
                with language(invoice.order.locale):
                    payments.append({
                        'PTID': '5',
                        'PTN': 'Lastschrift',
                        'PTNo1': None,
                        'PTNo2': None,
                        'PTNo3': None,
                        'PTNo4': ugettext('Event ticket {event}-{code}').format(
                            event=self.event.slug.upper(),
                            code=invoice.order.code
                        ),
                        'PTNo5': p.info_data.get('iban'),
                        'PTNo6': p.info_data.get('bic'),
                        'PTNo7': round(float(p.amount), 2),
                        'PTNo8': str(self.event.currency),
                        'PTNo9': p.info_data.get('date'),
                        'PTNo10': p.info_data.get('account'),
                        'PTNo11': None,
                        'PTNo12': None,
                        'PTNo13': None,
                        'PTNo14': p.info_data.get('reference'),
                        'PTNo15': p.full_id,
                    })
            elif p.provider.startswith('stripe'):
                src = p.info_data.get("source", "{}")
                payments.append({
                    'PTID': '81',
                    'PTN': 'Stripe',
                    'PTNo1': p.info_data.get("id"),
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': None,
                    'PTNo5': src.get("card", {}).get("last4"),
                    'PTNo6': None,
                    'PTNo7': round(float(p.amount), 2),
                    'PTNo8': str(self.event.currency),
                    'PTNo9': None,
                    'PTNo10': src.get('owner', {}).get('verified_name') or src.get('owner', {}).get('name'),
                    'PTNo11': None,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': None,
                    'PTNo15': p.full_id,
                })
            else:
                payments.append({
                    'PTID': '0',
                    'PTN': p.provider,
                    'PTNo1': None,
                    'PTNo2': None,
                    'PTNo3': None,
                    'PTNo4': None,
                    'PTNo5': None,
                    'PTNo6': None,
                    'PTNo7': str(p.amount),
                    'PTNo8': str(self.event.currency),
                    'PTNo9': None,
                    'PTNo10': None,
                    'PTNo11': None,
                    'PTNo12': None,
                    'PTNo13': None,
                    'PTNo14': None,
                    'PTNo15': p.full_id,
                })

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
            'DIC': None,
            'DICt': None,
            'DIDt': invoice.order.datetime.isoformat().replace('Z', '+00:00'),
            'DIZ': None,
            'DN': None,
            'DT': '30' if invoice.is_cancellation else '10',
            'EbNm': None,
            'EbPmtID': None,
            'EM': invoice.order.email,
            'FamN': invoice.invoice_to_name.rsplit(' ', 1)[-1],
            'FCExR': None,
            'FN': invoice.invoice_to_name.rsplit(' ', 1)[0] if ' ' in invoice.invoice_to_name else '',
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
            'PmDt': p_last.payment_date.isoformat().replace('Z', '+00:00') if p_last else None,
            'PPEm': paypal_email,  # todo: fill,
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
            'TGrossA': round(float(gross_total), 2),
            'TGrossAEUR': None,
            'TNetA': round(float(net_total), 2),
            'TNetAEUR': None,
            'TNo': None,
            'TT': None,
            'TVatA': round(float(gross_total - net_total), 2),
            'VatDp': False,
            'VatID': invoice.invoice_to_vat_id or None,
            'Zip': invoice.invoice_to_zipcode

        }

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
        return '{}_nrei.json'.format(self.event.slug), 'application/json', json.dumps(jo, cls=DjangoJSONEncoder, indent=4)


@receiver(register_data_exporters, dispatch_uid="exporter_dekodi_nrei")
def register_dekodi_export(sender, **kwargs):
    return DekodiNREIExporter
