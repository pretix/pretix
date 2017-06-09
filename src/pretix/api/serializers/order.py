from rest_framework import serializers

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import (
    Invoice, InvoiceAddress, InvoiceLine, Order, OrderPosition,
)


class InvoiceAdddressSerializer(I18nAwareModelSerializer):
    class Meta:
        model = InvoiceAddress
        fields = ('last_modified', 'company', 'name', 'street', 'zipcode', 'city', 'country', 'vat_id')


class OrderPositionSerializer(I18nAwareModelSerializer):
    class Meta:
        model = OrderPosition
        fields = ('id', 'positionid', 'item', 'variation', 'price', 'attendee_name', 'attendee_email', 'voucher',
                  'tax_rate', 'tax_value', 'secret', 'addon_to')


class OrderSerializer(I18nAwareModelSerializer):
    invoice_address = InvoiceAdddressSerializer()
    positions = OrderPositionSerializer(many=True)

    class Meta:
        model = Order
        fields = ('code', 'status', 'secret', 'email', 'locale', 'datetime', 'expires', 'payment_date',
                  'payment_provider', 'payment_fee', 'payment_fee_tax_rate', 'payment_fee_tax_value',
                  'total', 'comment', 'invoice_address', 'positions')


class InlineInvoiceLineSerializer(I18nAwareModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = ('description', 'gross_value', 'tax_value', 'tax_rate')


class InvoiceSerializer(I18nAwareModelSerializer):
    order = serializers.SlugRelatedField(slug_field='code', read_only=True)
    refers = serializers.SlugRelatedField(slug_field='invoice_no', read_only=True)
    lines = InlineInvoiceLineSerializer(many=True)

    class Meta:
        model = Invoice
        fields = ('order', 'invoice_no', 'is_cancellation', 'invoice_from', 'invoice_to', 'date', 'refers', 'locale',
                  'introductory_text', 'additional_text', 'payment_provider_text', 'footer_text', 'lines')
