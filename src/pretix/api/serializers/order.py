import json
from collections import Counter
from decimal import Decimal

import pycountry
from django.db.models import F, Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy
from django_countries.fields import Country
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.relations import SlugRelatedField
from rest_framework.reverse import reverse

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.channels import get_all_sales_channels
from pretix.base.i18n import language
from pretix.base.models import (
    Checkin, Invoice, InvoiceAddress, InvoiceLine, Item, ItemVariation, Order,
    OrderPosition, Question, QuestionAnswer, Seat, SubEvent, Voucher,
)
from pretix.base.models.orders import (
    CartPosition, OrderFee, OrderPayment, OrderRefund,
)
from pretix.base.pdf import get_variables
from pretix.base.services.cart import error_messages
from pretix.base.services.pricing import get_price
from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS
from pretix.base.signals import register_ticket_outputs
from pretix.multidomain.urlreverse import build_absolute_uri


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
                  'state', 'vat_id', 'vat_id_validated', 'internal_reference')
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
        if data.get('name_parts') and '_scheme' not in data.get('name_parts'):
            data['name_parts']['_scheme'] = self.context['request'].event.settings.name_scheme

        if data.get('country'):
            if not pycountry.countries.get(alpha_2=data.get('country')):
                raise ValidationError(
                    {'country': ['Invalid country code.']}
                )

        if data.get('state'):
            cc = str(data.get('country') or self.instance.country or '')
            if cc not in COUNTRIES_WITH_STATE_IN_ADDRESS:
                raise ValidationError(
                    {'state': ['States are not supported in country "{}".'.format(cc)]}
                )
            if not pycountry.subdivisions.get(code=cc + '-' + data.get('state')):
                raise ValidationError(
                    {'state': ['"{}" is not a known subdivision of the country "{}".'.format(data.get('state'), cc)]}
                )

        return data


class AnswerQuestionIdentifierField(serializers.Field):
    def to_representation(self, instance: QuestionAnswer):
        return instance.question.identifier


class AnswerQuestionOptionsIdentifierField(serializers.Field):
    def to_representation(self, instance: QuestionAnswer):
        return [o.identifier for o in instance.options.all()]


class InlineSeatSerializer(I18nAwareModelSerializer):

    class Meta:
        model = Seat
        fields = ('id', 'name', 'seat_guid')


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
        if not instance.generate_ticket:
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
        with language(instance.order.locale):
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
    seat = InlineSeatSerializer(read_only=True)

    class Meta:
        model = OrderPosition
        fields = ('id', 'order', 'positionid', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts',
                  'attendee_email', 'voucher', 'tax_rate', 'tax_value', 'secret', 'addon_to', 'subevent', 'checkins',
                  'downloads', 'answers', 'tax_rule', 'pseudonymization_id', 'pdf_data', 'seat')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'request' in self.context and not self.context['request'].query_params.get('pdf_data', 'false') == 'true':
            self.fields.pop('pdf_data')


class RequireAttentionField(serializers.Field):
    def to_representation(self, instance: OrderPosition):
        return instance.order.checkin_attention or instance.item.checkin_attention


class AttendeeNameField(serializers.Field):
    def to_representation(self, instance: OrderPosition):
        an = instance.attendee_name
        if not an:
            if instance.addon_to_id:
                an = instance.addon_to.attendee_name
        if not an:
            try:
                an = instance.order.invoice_address.name
            except InvoiceAddress.DoesNotExist:
                pass
        return an


class AttendeeNamePartsField(serializers.Field):
    def to_representation(self, instance: OrderPosition):
        an = instance.attendee_name
        p = instance.attendee_name_parts
        if not an:
            if instance.addon_to_id:
                an = instance.addon_to.attendee_name
                p = instance.addon_to.attendee_name_parts
        if not an:
            try:
                p = instance.order.invoice_address.name_parts
            except InvoiceAddress.DoesNotExist:
                pass
        return p


class CheckinListOrderPositionSerializer(OrderPositionSerializer):
    require_attention = RequireAttentionField(source='*')
    attendee_name = AttendeeNameField(source='*')
    attendee_name_parts = AttendeeNamePartsField(source='*')
    order__status = serializers.SlugRelatedField(read_only=True, slug_field='status', source='order')

    class Meta:
        model = OrderPosition
        fields = ('id', 'order', 'positionid', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts',
                  'attendee_email', 'voucher', 'tax_rate', 'tax_value', 'secret', 'addon_to', 'subevent', 'checkins',
                  'downloads', 'answers', 'tax_rule', 'pseudonymization_id', 'pdf_data', 'require_attention',
                  'order__status')


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


class PaymentURLField(serializers.URLField):
    def to_representation(self, instance: OrderPayment):
        if instance.state != OrderPayment.PAYMENT_STATE_CREATED:
            return None
        return build_absolute_uri(self.context['event'], 'presale:event.order.pay', kwargs={
            'order': instance.order.code,
            'secret': instance.order.secret,
            'payment': instance.pk,
        })


class OrderPaymentSerializer(I18nAwareModelSerializer):
    payment_url = PaymentURLField(source='*', allow_null=True, read_only=True)

    class Meta:
        model = OrderPayment
        fields = ('local_id', 'state', 'amount', 'created', 'payment_date', 'provider', 'payment_url')


class OrderRefundSerializer(I18nAwareModelSerializer):
    payment = SlugRelatedField(slug_field='local_id', read_only=True)

    class Meta:
        model = OrderRefund
        fields = ('local_id', 'state', 'source', 'amount', 'payment', 'created', 'execution_date', 'provider')


class OrderURLField(serializers.URLField):
    def to_representation(self, instance: Order):
        return build_absolute_uri(self.context['event'], 'presale:event.order', kwargs={
            'order': instance.code,
            'secret': instance.secret,
        })


class OrderSerializer(I18nAwareModelSerializer):
    invoice_address = InvoiceAddressSerializer(allow_null=True)
    positions = OrderPositionSerializer(many=True, read_only=True)
    fees = OrderFeeSerializer(many=True, read_only=True)
    downloads = OrderDownloadsField(source='*', read_only=True)
    payments = OrderPaymentSerializer(many=True, read_only=True)
    refunds = OrderRefundSerializer(many=True, read_only=True)
    payment_date = OrderPaymentDateField(source='*', read_only=True)
    payment_provider = OrderPaymentTypeField(source='*', read_only=True)
    url = OrderURLField(source='*', read_only=True)

    class Meta:
        model = Order
        fields = (
            'code', 'status', 'testmode', 'secret', 'email', 'locale', 'datetime', 'expires', 'payment_date',
            'payment_provider', 'fees', 'total', 'comment', 'invoice_address', 'positions', 'downloads',
            'checkin_attention', 'last_modified', 'payments', 'refunds', 'require_approval', 'sales_channel',
            'url'
        )
        read_only_fields = (
            'code', 'status', 'testmode', 'secret', 'datetime', 'expires', 'payment_date',
            'payment_provider', 'fees', 'total', 'positions', 'downloads',
            'last_modified', 'payments', 'refunds', 'require_approval', 'sales_channel'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context['request'].query_params.get('pdf_data', 'false') == 'true':
            self.fields['positions'].child.fields.pop('pdf_data')

    def validate_locale(self, l):
        if l not in set(k for k in self.instance.event.settings.locales):
            raise ValidationError('"{}" is not a supported locale for this event.'.format(l))
        return l

    def update(self, instance, validated_data):
        # Even though all fields that shouldn't be edited are marked as read_only in the serializer
        # (hopefully), we'll be extra careful here and be explicit about the model fields we update.
        update_fields = ['comment', 'checkin_attention', 'email', 'locale']

        if 'invoice_address' in validated_data:
            iadata = validated_data.pop('invoice_address')

            if not iadata:
                try:
                    instance.invoice_address.delete()
                except InvoiceAddress.DoesNotExist:
                    pass
            else:
                name = iadata.pop('name', '')
                if name and not iadata.get('name_parts'):
                    iadata['name_parts'] = {
                        '_legacy': name
                    }
                try:
                    ia = instance.invoice_address
                    if iadata.get('vat_id') != ia.vat_id:
                        ia.vat_id_validated = False
                    self.fields['invoice_address'].update(ia, iadata)
                except InvoiceAddress.DoesNotExist:
                    InvoiceAddress.objects.create(order=instance, **iadata)

        for attr, value in validated_data.items():
            if attr in update_fields:
                setattr(instance, attr, value)

        instance.save(update_fields=update_fields)
        return instance


class PriceCalcSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.none(), required=False, allow_null=True)
    variation = serializers.PrimaryKeyRelatedField(queryset=ItemVariation.objects.none(), required=False, allow_null=True)
    subevent = serializers.PrimaryKeyRelatedField(queryset=SubEvent.objects.none(), required=False, allow_null=True)
    locale = serializers.CharField(allow_null=True, required=False)

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = event.items.all()
        self.fields['variation'].queryset = ItemVariation.objects.filter(item__event=event)
        if event.has_subevents:
            self.fields['subevent'].queryset = event.subevents.all()
        else:
            del self.fields['subevent']


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
    attendee_name = serializers.CharField(required=False, allow_null=True)
    seat = serializers.CharField(required=False, allow_null=True)
    price = serializers.DecimalField(required=False, allow_null=True, decimal_places=2,
                                     max_digits=10)
    voucher = serializers.SlugRelatedField(slug_field='code', queryset=Voucher.objects.none(),
                                           required=False, allow_null=True)

    class Meta:
        model = OrderPosition
        fields = ('positionid', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts', 'attendee_email',
                  'secret', 'addon_to', 'subevent', 'answers', 'seat', 'voucher')

    def validate_secret(self, secret):
        if secret and OrderPosition.all.filter(order__event=self.context['event'], secret=secret).exists():
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
        if data.get('attendee_name_parts') and '_scheme' not in data.get('attendee_name_parts'):
            data['attendee_name_parts']['_scheme'] = self.context['request'].event.settings.name_scheme
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
    positions = OrderPositionCreateSerializer(many=True, required=True)
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
    payment_provider = serializers.CharField(required=False, allow_null=True)
    payment_info = CompatibleJSONField(required=False)
    consume_carts = serializers.ListField(child=serializers.CharField(), required=False)
    force = serializers.BooleanField(default=False, required=False)
    payment_date = serializers.DateTimeField(required=False, allow_null=True)
    send_mail = serializers.BooleanField(default=False, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['positions'].child.fields['voucher'].queryset = self.context['event'].vouchers.all()

    class Meta:
        model = Order
        fields = ('code', 'status', 'testmode', 'email', 'locale', 'payment_provider', 'fees', 'comment', 'sales_channel',
                  'invoice_address', 'positions', 'checkin_attention', 'payment_info', 'payment_date', 'consume_carts',
                  'force', 'send_mail')

    def validate_payment_provider(self, pp):
        if pp is None:
            return None
        if pp not in self.context['event'].get_payment_providers():
            raise ValidationError('The given payment provider is not known.')
        return pp

    def validate_sales_channel(self, channel):
        if channel not in get_all_sales_channels():
            raise ValidationError('Unknown sales channel.')
        return channel

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
        else:
            for i, p in enumerate(data):
                p['positionid'] = i + 1

        if any(errs):
            raise ValidationError(errs)
        return data

    def create(self, validated_data):
        fees_data = validated_data.pop('fees') if 'fees' in validated_data else []
        positions_data = validated_data.pop('positions') if 'positions' in validated_data else []
        payment_provider = validated_data.pop('payment_provider', None)
        payment_info = validated_data.pop('payment_info', '{}')
        payment_date = validated_data.pop('payment_date', now())
        force = validated_data.pop('force', False)
        self._send_mail = validated_data.pop('send_mail', False)

        if 'invoice_address' in validated_data:
            iadata = validated_data.pop('invoice_address')
            name = iadata.pop('name', '')
            if name and not iadata.get('name_parts'):
                iadata['name_parts'] = {
                    '_legacy': name
                }
            ia = InvoiceAddress(**iadata)
        else:
            ia = None

        with self.context['event'].lock() as now_dt:
            free_seats = set()
            seats_seen = set()
            consume_carts = validated_data.pop('consume_carts', [])
            delete_cps = []
            quota_avail_cache = {}
            voucher_usage = Counter()
            if consume_carts:
                for cp in CartPosition.objects.filter(
                    event=self.context['event'], cart_id__in=consume_carts, expires__gt=now()
                ):
                    quotas = (cp.variation.quotas.filter(subevent=cp.subevent)
                              if cp.variation else cp.item.quotas.filter(subevent=cp.subevent))
                    for quota in quotas:
                        if quota not in quota_avail_cache:
                            quota_avail_cache[quota] = list(quota.availability())
                        if quota_avail_cache[quota][1] is not None:
                            quota_avail_cache[quota][1] += 1
                    if cp.voucher:
                        voucher_usage[cp.voucher] -= 1
                    if cp.expires > now_dt:
                        if cp.seat:
                            free_seats.add(cp.seat)
                    delete_cps.append(cp)

            errs = [{} for p in positions_data]

            for i, pos_data in enumerate(positions_data):
                if pos_data.get('voucher'):
                    v = pos_data['voucher']

                    if not v.applies_to(pos_data['item'], pos_data.get('variation')):
                        errs[i]['voucher'] = [error_messages['voucher_invalid_item']]
                        continue

                    if v.subevent_id and pos_data.get('subevent').pk != v.subevent_id:
                        errs[i]['voucher'] = [error_messages['voucher_invalid_subevent']]
                        continue

                    if v.valid_until is not None and v.valid_until < now_dt:
                        errs[i]['voucher'] = [error_messages['voucher_expired']]
                        continue

                    voucher_usage[v] += 1
                    if voucher_usage[v] > 0:
                        redeemed_in_carts = CartPosition.objects.filter(
                            Q(voucher=pos_data['voucher']) & Q(event=self.context['event']) & Q(expires__gte=now_dt)
                        ).exclude(pk__in=[cp.pk for cp in delete_cps])
                        v_avail = v.max_usages - v.redeemed - redeemed_in_carts.count()
                        if v_avail < voucher_usage[v]:
                            errs[i]['voucher'] = [
                                'The voucher has already been used the maximum number of times.'
                            ]

                seated = pos_data.get('item').seat_category_mappings.filter(subevent=pos_data.get('subevent')).exists()
                if pos_data.get('seat'):
                    if not seated:
                        errs[i]['seat'] = ['The specified product does not allow to choose a seat.']
                    try:
                        seat = self.context['event'].seats.get(seat_guid=pos_data['seat'], subevent=pos_data.get('subevent'))
                    except Seat.DoesNotExist:
                        errs[i]['seat'] = ['The specified seat does not exist.']
                    else:
                        pos_data['seat'] = seat
                        if (seat not in free_seats and not seat.is_available()) or seat in seats_seen:
                            errs[i]['seat'] = [ugettext_lazy('The selected seat "{seat}" is not available.').format(seat=seat.name)]
                        seats_seen.add(seat)
                elif seated:
                    errs[i]['seat'] = ['The specified product requires to choose a seat.']

            if not force:
                for i, pos_data in enumerate(positions_data):
                    if pos_data.get('voucher'):
                        if pos_data['voucher'].allow_ignore_quota or pos_data['voucher'].block_quota:
                            continue

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

            if any(errs):
                raise ValidationError({'positions': errs})

            if validated_data.get('locale', None) is None:
                validated_data['locale'] = self.context['event'].settings.locale
            order = Order(event=self.context['event'], **validated_data)
            order.set_expires(subevents=[p.get('subevent') for p in positions_data])
            order.meta_info = "{}"
            order.total = Decimal('0.00')
            order.save()

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
                if addon_to:
                    pos.addon_to = pos_map[addon_to]

                if pos.price is None:
                    price = get_price(
                        item=pos.item,
                        variation=pos.variation,
                        voucher=pos.voucher,
                        custom_price=None,
                        subevent=pos.subevent,
                        addon_to=pos.addon_to,
                        invoice_address=ia,
                    )
                    pos.price = price.gross
                    pos.tax_rate = price.rate
                    pos.tax_value = price.tax
                    pos.tax_rule = pos.item.tax_rule
                else:
                    pos._calculate_tax()
                if pos.voucher:
                    Voucher.objects.filter(pk=pos.voucher.pk).update(redeemed=F('redeemed') + 1)
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

        order.total = sum([p.price for p in order.positions.all()]) + sum([f.value for f in order.fees.all()])
        order.save(update_fields=['total'])

        if order.total == Decimal('0.00') and validated_data.get('status') != Order.STATUS_PAID:
            order.status = Order.STATUS_PAID
            order.save()
            order.payments.create(
                amount=order.total, provider='free', state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                payment_date=now()
            )
        elif payment_provider == "free" and order.total != Decimal('0.00'):
            raise ValidationError('You cannot use the "free" payment provider for non-free orders.')
        elif validated_data.get('status') == Order.STATUS_PAID:
            if not payment_provider:
                raise ValidationError('You cannot create a paid order without a payment provider.')
            order.payments.create(
                amount=order.total,
                provider=payment_provider,
                info=payment_info,
                payment_date=payment_date,
                state=OrderPayment.PAYMENT_STATE_CONFIRMED
            )
        elif payment_provider:
            order.payments.create(
                amount=order.total,
                provider=payment_provider,
                info=payment_info,
                state=OrderPayment.PAYMENT_STATE_CREATED
            )

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
