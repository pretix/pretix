import json
from collections import Counter
from decimal import Decimal

from django.utils.timezone import now
from django.utils.translation import ugettext_lazy
from django_countries.fields import Country
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.relations import SlugRelatedField
from rest_framework.reverse import reverse

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import (
    Checkin, Invoice, InvoiceAddress, InvoiceLine, Order, OrderPosition,
    Question, QuestionAnswer,
)
from pretix.base.models.orders import (
    CartPosition, OrderFee, OrderPayment, OrderRefund,
)
from pretix.base.pdf import get_variables
from pretix.base.signals import register_ticket_outputs


class CompatibleCountryField(serializers.Field):
    def to_internal_value(self, data):
        return {self.field_name: Country(data)}

    def to_representation(self, instance: InvoiceAddress):
        if instance.country:
            return str(instance.country)
        else:
            return instance.country_old


class InvoiceAddressSerializer(I18nAwareModelSerializer):
    country = CompatibleCountryField(source='*')
    name = serializers.CharField(required=False)

    class Meta:
        model = InvoiceAddress
        fields = ('last_modified', 'is_business', 'company', 'name', 'name_parts', 'street', 'zipcode', 'city', 'country',
                  'vat_id', 'vat_id_validated', 'internal_reference')
        read_only_fields = ('last_modified', 'vat_id_validated')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for v in self.fields.values():
            v.required = False
            v.allow_blank = True

    def validate(self, data):
        if data.get('name') and data.get('name_parts'):
            raise ValidationError(
                {'name': ['Do not specify name if you specified name_parts.']}
            )
        return data


class AnswerQuestionIdentifierField(serializers.Field):
    def to_representation(self, instance: QuestionAnswer):
        return instance.question.identifier


class AnswerQuestionOptionsIdentifierField(serializers.Field):
    def to_representation(self, instance: QuestionAnswer):
        return [o.identifier for o in instance.options.all()]


class AnswerSerializer(I18nAwareModelSerializer):
    question_identifier = AnswerQuestionIdentifierField(source='*', read_only=True)
    option_identifiers = AnswerQuestionOptionsIdentifierField(source='*', read_only=True)

    class Meta:
        model = QuestionAnswer
        fields = ('question', 'answer', 'question_identifier', 'options', 'option_identifiers')


class CheckinSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Checkin
        fields = ('datetime', 'list')


class OrderDownloadsField(serializers.Field):
    def to_representation(self, instance: Order):
        if instance.status != Order.STATUS_PAID:
            if instance.status != Order.STATUS_PENDING or instance.require_approval or not instance.event.settings.ticket_download_pending:
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
            if instance.order.status != Order.STATUS_PENDING or instance.order.require_approval or not instance.order.event.settings.ticket_download_pending:
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


class PdfDataSerializer(serializers.Field):
    def to_representation(self, instance: OrderPosition):
        res = {}

        ev = instance.subevent or instance.order.event
        # This needs to have some extra performance improvements to avoid creating hundreds of queries when
        # we serialize a list.

        if 'vars' not in self.context:
            self.context['vars'] = get_variables(self.context['request'].event)

        for k, f in self.context['vars'].items():
            res[k] = f['evaluate'](instance, instance.order, ev)

        if not hasattr(ev, '_cached_meta_data'):
            ev._cached_meta_data = ev.meta_data

        for k, v in ev._cached_meta_data.items():
            res['meta:' + k] = v

        return res


class OrderPositionSerializer(I18nAwareModelSerializer):
    checkins = CheckinSerializer(many=True)
    answers = AnswerSerializer(many=True)
    downloads = PositionDownloadsField(source='*')
    order = serializers.SlugRelatedField(slug_field='code', read_only=True)
    pdf_data = PdfDataSerializer(source='*')

    class Meta:
        model = OrderPosition
        fields = ('id', 'order', 'positionid', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts',
                  'attendee_email', 'voucher', 'tax_rate', 'tax_value', 'secret', 'addon_to', 'subevent', 'checkins',
                  'downloads', 'answers', 'tax_rule', 'pseudonymization_id', 'pdf_data')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'request' in self.context and not self.context['request'].query_params.get('pdf_data', 'false') == 'true':
            self.fields.pop('pdf_data')


class OrderPaymentTypeField(serializers.Field):
    # TODO: Remove after pretix 2.2
    def to_representation(self, instance: Order):
        t = None
        for p in instance.payments.all():
            t = p.provider
        return t


class OrderPaymentDateField(serializers.DateField):
    # TODO: Remove after pretix 2.2
    def to_representation(self, instance: Order):
        t = None
        for p in instance.payments.all():
            t = p.payment_date or t
        if t:

            return super().to_representation(t.date())


class OrderFeeSerializer(I18nAwareModelSerializer):
    class Meta:
        model = OrderFee
        fields = ('fee_type', 'value', 'description', 'internal_type', 'tax_rate', 'tax_value', 'tax_rule')


class OrderPaymentSerializer(I18nAwareModelSerializer):
    class Meta:
        model = OrderPayment
        fields = ('local_id', 'state', 'amount', 'created', 'payment_date', 'provider')


class OrderRefundSerializer(I18nAwareModelSerializer):
    payment = SlugRelatedField(slug_field='local_id', read_only=True)

    class Meta:
        model = OrderRefund
        fields = ('local_id', 'state', 'source', 'amount', 'payment', 'created', 'execution_date', 'provider')


class OrderSerializer(I18nAwareModelSerializer):
    invoice_address = InvoiceAddressSerializer()
    positions = OrderPositionSerializer(many=True)
    fees = OrderFeeSerializer(many=True)
    downloads = OrderDownloadsField(source='*')
    payments = OrderPaymentSerializer(many=True)
    refunds = OrderRefundSerializer(many=True)
    payment_date = OrderPaymentDateField(source='*')
    payment_provider = OrderPaymentTypeField(source='*')

    class Meta:
        model = Order
        fields = ('code', 'status', 'secret', 'email', 'locale', 'datetime', 'expires', 'payment_date',
                  'payment_provider', 'fees', 'total', 'comment', 'invoice_address', 'positions', 'downloads',
                  'checkin_attention', 'last_modified', 'payments', 'refunds', 'require_approval')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context['request'].query_params.get('pdf_data', 'false') == 'true':
            self.fields['positions'].child.fields.pop('pdf_data')


class AnswerCreateSerializer(I18nAwareModelSerializer):

    class Meta:
        model = QuestionAnswer
        fields = ('question', 'answer', 'options')

    def validate_question(self, q):
        if q.event != self.context['event']:
            raise ValidationError(
                'The specified question does not belong to this event.'
            )
        return q

    def validate(self, data):
        if data.get('question').type == Question.TYPE_FILE:
            raise ValidationError(
                'File uploads are currently not supported via the API.'
            )
        elif data.get('question').type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
            if not data.get('options'):
                raise ValidationError(
                    'You need to specify options if the question is of a choice type.'
                )
            if data.get('question').type == Question.TYPE_CHOICE and len(data.get('options')) > 1:
                raise ValidationError(
                    'You can specify at most one option for this question.'
                )
            data['answer'] = ", ".join([str(o) for o in data.get('options')])

        else:
            if data.get('options'):
                raise ValidationError(
                    'You should not specify options if the question is not of a choice type.'
                )

            if data.get('question').type == Question.TYPE_BOOLEAN:
                if data.get('answer') in ['true', 'True', '1', 'TRUE']:
                    data['answer'] = 'True'
                elif data.get('answer') in ['false', 'False', '0', 'FALSE']:
                    data['answer'] = 'False'
                else:
                    raise ValidationError(
                        'Please specify "true" or "false" for boolean questions.'
                    )
            elif data.get('question').type == Question.TYPE_NUMBER:
                serializers.DecimalField(
                    max_digits=50,
                    decimal_places=25
                ).to_internal_value(data.get('answer'))
            elif data.get('question').type == Question.TYPE_DATE:
                data['answer'] = serializers.DateField().to_internal_value(data.get('answer'))
            elif data.get('question').type == Question.TYPE_TIME:
                data['answer'] = serializers.TimeField().to_internal_value(data.get('answer'))
            elif data.get('question').type == Question.TYPE_DATETIME:
                data['answer'] = serializers.DateTimeField().to_internal_value(data.get('answer'))
        return data


class OrderFeeCreateSerializer(I18nAwareModelSerializer):
    class Meta:
        model = OrderFee
        fields = ('fee_type', 'value', 'description', 'internal_type', 'tax_rule')

    def validate_tax_rule(self, tr):
        if tr and tr.event != self.context['event']:
            raise ValidationError(
                'The specified tax rate does not belong to this event.'
            )
        return tr


class OrderPositionCreateSerializer(I18nAwareModelSerializer):
    answers = AnswerCreateSerializer(many=True, required=False)
    addon_to = serializers.IntegerField(required=False, allow_null=True)
    secret = serializers.CharField(required=False)
    attendee_name = serializers.CharField(required=False)

    class Meta:
        model = OrderPosition
        fields = ('positionid', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts', 'attendee_email',
                  'secret', 'addon_to', 'subevent', 'answers')

    def validate_secret(self, secret):
        if secret and OrderPosition.objects.filter(order__event=self.context['event'], secret=secret).exists():
            raise ValidationError(
                'You cannot assign a position secret that already exists.'
            )
        return secret

    def validate_item(self, item):
        if item.event != self.context['event']:
            raise ValidationError(
                'The specified item does not belong to this event.'
            )
        if not item.active:
            raise ValidationError(
                'The specified item is not active.'
            )
        return item

    def validate_subevent(self, subevent):
        if self.context['event'].has_subevents:
            if not subevent:
                raise ValidationError(
                    'You need to set a subevent.'
                )
            if subevent.event != self.context['event']:
                raise ValidationError(
                    'The specified subevent does not belong to this event.'
                )
        elif subevent:
            raise ValidationError(
                'You cannot set a subevent for this event.'
            )
        return subevent

    def validate(self, data):
        if data.get('item'):
            if data.get('item').has_variations:
                if not data.get('variation'):
                    raise ValidationError({'variation': ['You should specify a variation for this item.']})
                else:
                    if data.get('variation').item != data.get('item'):
                        raise ValidationError(
                            {'variation': ['The specified variation does not belong to the specified item.']}
                        )
            elif data.get('variation'):
                raise ValidationError(
                    {'variation': ['You cannot specify a variation for this item.']}
                )
        if data.get('attendee_name') and data.get('attendee_name_parts'):
            raise ValidationError(
                {'attendee_name': ['Do not specify attendee_name if you specified attendee_name_parts.']}
            )
        return data


class CompatibleJSONField(serializers.JSONField):
    def to_internal_value(self, data):
        try:
            return json.dumps(data)
        except (TypeError, ValueError):
            self.fail('invalid')

    def to_representation(self, value):
        if value:
            return json.loads(value)
        return value


class OrderCreateSerializer(I18nAwareModelSerializer):
    invoice_address = InvoiceAddressSerializer(required=False)
    positions = OrderPositionCreateSerializer(many=True, required=False)
    fees = OrderFeeCreateSerializer(many=True, required=False)
    status = serializers.ChoiceField(choices=(
        ('n', Order.STATUS_PENDING),
        ('p', Order.STATUS_PAID),
    ), default='n', required=False)
    code = serializers.CharField(
        required=False,
        max_length=16,
        min_length=5
    )
    comment = serializers.CharField(required=False, allow_blank=True)
    payment_provider = serializers.CharField(required=True)
    payment_info = CompatibleJSONField(required=False)
    consume_carts = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = Order
        fields = ('code', 'status', 'email', 'locale', 'payment_provider', 'fees', 'comment',
                  'invoice_address', 'positions', 'checkin_attention', 'payment_info', 'consume_carts')

    def validate_payment_provider(self, pp):
        if pp not in self.context['event'].get_payment_providers():
            raise ValidationError('The given payment provider is not known.')
        return pp

    def validate_code(self, code):
        if code and Order.objects.filter(event__organizer=self.context['event'].organizer, code=code).exists():
            raise ValidationError(
                'This order code is already in use.'
            )
        if any(c not in 'ABCDEFGHJKLMNPQRSTUVWXYZ1234567890' for c in code):
            raise ValidationError(
                'This order code contains invalid characters.'
            )
        return code

    def validate_positions(self, data):
        if not data:
            raise ValidationError(
                'An order cannot be empty.'
            )
        errs = [{} for p in data]
        if any([p.get('positionid') for p in data]):
            if not all([p.get('positionid') for p in data]):
                for i, p in enumerate(data):
                    if not p.get('positionid'):
                        errs[i]['positionid'] = [
                            'If you set position IDs manually, you need to do so for all positions.'
                        ]
                raise ValidationError(errs)

            last_non_add_on = None
            last_posid = 0

            for i, p in enumerate(data):
                if p['positionid'] != last_posid + 1:
                    errs[i]['positionid'] = [
                        'Position IDs need to be consecutive.'
                    ]
                if p.get('addon_to') and p['addon_to'] != last_non_add_on:
                    errs[i]['addon_to'] = [
                        "If you set addon_to, you need to make sure that the referenced "
                        "position ID exists and is transmitted directly before its add-ons."
                    ]

                if not p.get('addon_to'):
                    last_non_add_on = p['positionid']
                last_posid = p['positionid']

        elif any([p.get('addon_to') for p in data]):
            errs = [
                {'positionid': ["If you set addon_to on any position, you need to specify position IDs manually."]}
                for p in data
            ]

        if any(errs):
            raise ValidationError(errs)
        return data

    def create(self, validated_data):
        fees_data = validated_data.pop('fees') if 'fees' in validated_data else []
        positions_data = validated_data.pop('positions') if 'positions' in validated_data else []
        payment_provider = validated_data.pop('payment_provider')
        payment_info = validated_data.pop('payment_info', '{}')

        if 'invoice_address' in validated_data:
            iadata = validated_data.pop('invoice_address')
            name = iadata.pop('name', '')
            if name and not iadata.get('name_parts'):
                iadata['name_parts'] = {
                    '_legacy': name
                }
            ia = InvoiceAddress(**iadata)
            ia.set_name(iadata['name_parts'], self.context['event'])
        else:
            ia = None

        with self.context['event'].lock() as now_dt:
            quotadiff = Counter()

            consume_carts = validated_data.pop('consume_carts', [])
            delete_cps = []
            quota_avail_cache = {}
            if consume_carts:
                for cp in CartPosition.objects.filter(event=self.context['event'], cart_id__in=consume_carts):
                    quotas = (cp.variation.quotas.filter(subevent=cp.subevent)
                              if cp.variation else cp.item.quotas.filter(subevent=cp.subevent))
                    for quota in quotas:
                        if quota not in quota_avail_cache:
                            quota_avail_cache[quota] = list(quota.availability())
                        if quota_avail_cache[quota][1] is not None:
                            quota_avail_cache[quota][1] += 1
                    if cp.expires > now_dt:
                        quotadiff.subtract(quotas)
                    delete_cps.append(cp)

            errs = [{} for p in positions_data]

            for i, pos_data in enumerate(positions_data):
                new_quotas = (pos_data.get('variation').quotas.filter(subevent=pos_data.get('subevent'))
                              if pos_data.get('variation')
                              else pos_data.get('item').quotas.filter(subevent=pos_data.get('subevent')))
                if len(new_quotas) == 0:
                    errs[i]['item'] = [ugettext_lazy('The product "{}" is not assigned to a quota.').format(
                        str(pos_data.get('item'))
                    )]
                else:
                    for quota in new_quotas:
                        if quota not in quota_avail_cache:
                            quota_avail_cache[quota] = list(quota.availability())

                        if quota_avail_cache[quota][1] is not None:
                            quota_avail_cache[quota][1] -= 1
                            if quota_avail_cache[quota][1] < 0:
                                errs[i]['item'] = [
                                    ugettext_lazy('There is not enough quota available on quota "{}" to perform the operation.').format(
                                        quota.name
                                    )
                                ]

                quotadiff.update(new_quotas)

            if any(errs):
                raise ValidationError({'positions': errs})

            if validated_data.get('locale', None) is None:
                validated_data['locale'] = self.context['event'].settings.locale
            order = Order(event=self.context['event'], **validated_data)
            order.set_expires(subevents=[p.get('subevent') for p in positions_data])
            order.total = sum([p['price'] for p in positions_data]) + sum([f['value'] for f in fees_data], Decimal('0.00'))
            order.meta_info = "{}"
            order.save()

            if order.total == Decimal('0.00') and validated_data.get('status') != Order.STATUS_PAID:
                order.status = Order.STATUS_PAID
                order.save()
                order.payments.create(
                    amount=order.total, provider='free', state=OrderPayment.PAYMENT_STATE_CONFIRMED
                )
            elif payment_provider == "free" and order.total != Decimal('0.00'):
                raise ValidationError('You cannot use the "free" payment provider for non-free orders.')
            elif validated_data.get('status') == Order.STATUS_PAID:
                order.payments.create(
                    amount=order.total,
                    provider=payment_provider,
                    info=payment_info,
                    payment_date=now(),
                    state=OrderPayment.PAYMENT_STATE_CONFIRMED
                )
            elif payment_provider:
                order.payments.create(
                    amount=order.total,
                    provider=payment_provider,
                    info=payment_info,
                    state=OrderPayment.PAYMENT_STATE_CREATED
                )

            if ia:
                ia.order = order
                ia.save()
            pos_map = {}
            for pos_data in positions_data:
                answers_data = pos_data.pop('answers', [])
                addon_to = pos_data.pop('addon_to', None)
                attendee_name = pos_data.pop('attendee_name', '')
                if attendee_name and not pos_data.get('attendee_name_parts'):
                    pos_data['attendee_name_parts'] = {
                        '_legacy': attendee_name
                    }
                pos = OrderPosition(**pos_data)
                pos.order = order
                pos._calculate_tax()
                if addon_to:
                    pos.addon_to = pos_map[addon_to]
                pos.save()
                pos_map[pos.positionid] = pos
                for answ_data in answers_data:
                    options = answ_data.pop('options', [])
                    answ = pos.answers.create(**answ_data)
                    answ.options.add(*options)

            for cp in delete_cps:
                cp.delete()
        for fee_data in fees_data:
            f = OrderFee(**fee_data)
            f.order = order
            f._calculate_tax()
            f.save()

        return order


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


class OrderRefundCreateSerializer(I18nAwareModelSerializer):
    payment = serializers.IntegerField(required=False, allow_null=True)
    provider = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    info = CompatibleJSONField(required=False)

    class Meta:
        model = OrderRefund
        fields = ('state', 'source', 'amount', 'payment', 'execution_date', 'provider', 'info')

    def create(self, validated_data):
        pid = validated_data.pop('payment', None)
        if pid:
            try:
                p = self.context['order'].payments.get(local_id=pid)
            except OrderPayment.DoesNotExist:
                raise ValidationError('Unknown payment ID.')
        else:
            p = None

        order = OrderRefund(order=self.context['order'], payment=p, **validated_data)
        order.save()
        return order
