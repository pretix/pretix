from decimal import Decimal

from rest_framework import serializers
from rest_framework.reverse import reverse

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import (
    Checkin, Invoice, InvoiceAddress, InvoiceLine, Order, OrderPosition,
    QuestionAnswer,
)
from pretix.base.models.orders import OrderFee
from pretix.base.signals import register_ticket_outputs


class CompatibleCountryField(serializers.Field):
    def to_representation(self, instance: InvoiceAddress):
        if instance.country:
            return str(instance.country)
        else:
            return instance.country_old


class InvoiceAdddressSerializer(I18nAwareModelSerializer):
    country = CompatibleCountryField(source='*')

    class Meta:
        model = InvoiceAddress
        fields = ('last_modified', 'is_business', 'company', 'name', 'street', 'zipcode', 'city', 'country', 'vat_id',
                  'vat_id_validated', 'internal_reference')


class AnswerSerializer(I18nAwareModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ('question', 'answer', 'options')


class CheckinSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Checkin
        fields = ('datetime', 'list')


class OrderDownloadsField(serializers.Field):
    def to_representation(self, instance: Order):
        if instance.status != Order.STATUS_PAID:
            return []

        request = self.context['request']
        res = []
        responses = register_ticket_outputs.send(instance.event)
        for receiver, response in responses:
            provider = response(instance.event)
            if provider.is_enabled:
                res.append({
                    'output': provider.identifier,
                    'url': reverse('api-v1:order-download', kwargs={
                        'organizer': instance.event.organizer.slug,
                        'event': instance.event.slug,
                        'code': instance.code,
                        'output': provider.identifier,
                    }, request=request)
                })
        return res


class PositionDownloadsField(serializers.Field):
    def to_representation(self, instance: OrderPosition):
        if instance.order.status != Order.STATUS_PAID:
            return []
        if instance.addon_to_id and not instance.order.event.settings.ticket_download_addons:
            return []
        if not instance.item.admission and not instance.order.event.settings.ticket_download_nonadm:
            return []

        request = self.context['request']
        res = []
        responses = register_ticket_outputs.send(instance.order.event)
        for receiver, response in responses:
            provider = response(instance.order.event)
            if provider.is_enabled:
                res.append({
                    'output': provider.identifier,
                    'url': reverse('api-v1:orderposition-download', kwargs={
                        'organizer': instance.order.event.organizer.slug,
                        'event': instance.order.event.slug,
                        'pk': instance.pk,
                        'output': provider.identifier,
                    }, request=request)
                })
        return res


class OrderPositionSerializer(I18nAwareModelSerializer):
    checkins = CheckinSerializer(many=True)
    answers = AnswerSerializer(many=True)
    downloads = PositionDownloadsField(source='*')
    order = serializers.SlugRelatedField(slug_field='code', read_only=True)

    class Meta:
        model = OrderPosition
        fields = ('id', 'order', 'positionid', 'item', 'variation', 'price', 'attendee_name', 'attendee_email',
                  'voucher', 'tax_rate', 'tax_value', 'secret', 'addon_to', 'subevent', 'checkins', 'downloads',
                  'answers', 'tax_rule')


class OrderFeeSerializer(I18nAwareModelSerializer):
    class Meta:
        model = OrderFee
        fields = ('fee_type', 'value', 'description', 'internal_type', 'tax_rate', 'tax_value', 'tax_rule')


class PaymentFeeLegacyField(serializers.Field):
    def __init__(self, *args, **kwargs):
        self.attr = kwargs.pop('attribute')
        super().__init__(*args, **kwargs)

    def to_representation(self, instance: Order):
        return str(
            sum([getattr(f, self.attr) for f in instance.fees.all() if f.fee_type == OrderFee.FEE_TYPE_PAYMENT],
                Decimal('0.00'))
        )


class OrderSerializer(I18nAwareModelSerializer):
    invoice_address = InvoiceAdddressSerializer()
    positions = OrderPositionSerializer(many=True)
    fees = OrderFeeSerializer(many=True)
    downloads = OrderDownloadsField(source='*')
    payment_fee = PaymentFeeLegacyField(source='*', attribute='value')  # TODO: Remove in 1.9
    payment_fee_tax_rate = PaymentFeeLegacyField(source='*', attribute='tax_rate')  # TODO: Remove in 1.9
    payment_fee_tax_value = PaymentFeeLegacyField(source='*', attribute='tax_value')  # TODO: Remove in 1.9

    class Meta:
        model = Order
        fields = ('code', 'status', 'secret', 'email', 'locale', 'datetime', 'expires', 'payment_date',
                  'payment_provider', 'fees', 'total', 'comment', 'invoice_address', 'positions', 'downloads',
                  'payment_fee', 'payment_fee_tax_rate', 'payment_fee_tax_value', 'checkin_attention')


class InlineInvoiceLineSerializer(I18nAwareModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = ('description', 'gross_value', 'tax_value', 'tax_rate', 'tax_name')


class InvoiceSerializer(I18nAwareModelSerializer):
    order = serializers.SlugRelatedField(slug_field='code', read_only=True)
    refers = serializers.SlugRelatedField(slug_field='invoice_no', read_only=True)
    lines = InlineInvoiceLineSerializer(many=True)

    class Meta:
        model = Invoice
        fields = ('order', 'number', 'is_cancellation', 'invoice_from', 'invoice_to', 'date', 'refers', 'locale',
                  'introductory_text', 'additional_text', 'payment_provider_text', 'footer_text', 'lines',
                  'foreign_currency_display', 'foreign_currency_rate', 'foreign_currency_rate_date',
                  'internal_reference')
