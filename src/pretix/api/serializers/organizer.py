#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import logging
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers import AsymmetricField
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField
from pretix.api.serializers.settings import SettingsSerializer
from pretix.base.auth import get_auth_backends
from pretix.base.i18n import get_language_without_region
from pretix.base.models import (
    Customer, Device, GiftCard, GiftCardAcceptance, GiftCardTransaction,
    Membership, MembershipType, OrderPosition, Organizer, ReusableMedium,
    SeatingPlan, Team, TeamAPIToken, TeamInvite, User,
)
from pretix.base.models.seating import SeatingPlanLayoutValidator
from pretix.base.services.mail import SendMailException, mail
from pretix.base.settings import validate_organizer_settings
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri

logger = logging.getLogger(__name__)


class OrganizerSerializer(I18nAwareModelSerializer):
    public_url = serializers.SerializerMethodField('get_organizer_url', read_only=True)

    def get_organizer_url(self, organizer):
        return build_absolute_uri(organizer, 'presale:organizer.index')

    class Meta:
        model = Organizer
        fields = ('name', 'slug', 'public_url')


class SeatingPlanSerializer(I18nAwareModelSerializer):
    layout = CompatibleJSONField(
        validators=[SeatingPlanLayoutValidator()]
    )

    class Meta:
        model = SeatingPlan
        fields = ('id', 'name', 'layout')


class CustomerSerializer(I18nAwareModelSerializer):
    identifier = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)
    last_modified = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Customer
        fields = ('identifier', 'external_identifier', 'email', 'name', 'name_parts', 'is_active', 'is_verified', 'last_login', 'date_joined',
                  'locale', 'last_modified', 'notes')

    def update(self, instance, validated_data):
        if instance and instance.provider_id:
            validated_data['external_identifier'] = instance.external_identifier
        return super().update(instance, validated_data)

    def validate(self, data):
        if data.get('name_parts') and not isinstance(data.get('name_parts'), dict):
            raise ValidationError({'name_parts': ['Invalid data type']})
        if data.get('name_parts') and '_scheme' not in data.get('name_parts'):
            data['name_parts']['_scheme'] = self.context['request'].organizer.settings.name_scheme
        return data


class CustomerCreateSerializer(CustomerSerializer):
    send_email = serializers.BooleanField(default=False, required=False, allow_null=True)
    password = serializers.CharField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Customer
        fields = CustomerSerializer.Meta.fields + ('send_email', 'password')


class MembershipTypeSerializer(I18nAwareModelSerializer):

    class Meta:
        model = MembershipType
        fields = ('id', 'name', 'transferable', 'allow_parallel_usage', 'max_usages')


class MembershipSerializer(I18nAwareModelSerializer):
    customer = serializers.SlugRelatedField(slug_field='identifier', queryset=Customer.objects.none())

    class Meta:
        model = Membership
        fields = ('id', 'testmode', 'customer', 'membership_type', 'date_start', 'date_end', 'attendee_name_parts')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = self.context['organizer'].customers.all()
        self.fields['membership_type'].queryset = self.context['organizer'].membership_types.all()

    def update(self, instance, validated_data):
        validated_data['customer'] = instance.customer  # no modifying
        validated_data['testmode'] = instance.testmode  # no modifying
        return super().update(instance, validated_data)


class FlexibleTicketRelatedField(serializers.PrimaryKeyRelatedField):

    def to_internal_value(self, data):
        queryset = self.get_queryset()

        if isinstance(data, int):
            try:
                return queryset.get(pk=data)
            except ObjectDoesNotExist:
                self.fail('does_not_exist', pk_value=data)

        elif isinstance(data, str):
            try:
                return queryset.get(
                    Q(secret=data)
                    | Q(pseudonymization_id=data)
                    | Q(pk__in=ReusableMedium.objects.filter(
                        organizer=self.context['organizer'],
                        type='barcode',
                        identifier=data
                    ))
                )
            except ObjectDoesNotExist:
                self.fail('does_not_exist', pk_value=data)

        self.fail('incorrect_type', data_type=type(data).__name__)


class GiftCardSerializer(I18nAwareModelSerializer):
    value = serializers.DecimalField(max_digits=13, decimal_places=2, min_value=Decimal('0.00'))
    owner_ticket = FlexibleTicketRelatedField(required=False, allow_null=True, queryset=OrderPosition.all.none())
    issuer = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['owner_ticket'].queryset = OrderPosition.objects.filter(order__event__organizer=self.context['organizer'])

        if 'owner_ticket' in self.context['request'].query_params.getlist('expand'):
            from pretix.api.serializers.media import (
                NestedOrderPositionSerializer,
            )

            self.fields['owner_ticket'] = AsymmetricField(
                NestedOrderPositionSerializer(read_only=True, context=self.context),
                self.fields['owner_ticket'],
            )

    def validate(self, data):
        data = super().validate(data)
        if 'secret' in data:
            s = data['secret']
            qs = GiftCard.objects.filter(
                secret=s
            ).filter(
                Q(issuer=self.context["organizer"]) |
                Q(issuer__in=GiftCardAcceptance.objects.filter(
                    acceptor=self.context["organizer"],
                    active=True,
                ).values_list('issuer', flat=True))
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    {'secret': _(
                        'A gift card with the same secret already exists in your or an affiliated organizer account.')}
                )
        return data

    class Meta:
        model = GiftCard
        fields = ('id', 'secret', 'issuance', 'value', 'currency', 'testmode', 'expires', 'conditions', 'owner_ticket',
                  'issuer')


class OrderEventSlugField(serializers.RelatedField):

    def to_representation(self, obj):
        return obj.event.slug


class GiftCardTransactionSerializer(I18nAwareModelSerializer):
    order = serializers.SlugRelatedField(slug_field='code', read_only=True)
    acceptor = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    event = OrderEventSlugField(source='order', read_only=True)

    class Meta:
        model = GiftCardTransaction
        fields = ('id', 'datetime', 'value', 'event', 'order', 'text', 'info', 'acceptor')


class EventSlugField(serializers.SlugRelatedField):
    def get_queryset(self):
        return self.context['organizer'].events.all()


class TeamSerializer(serializers.ModelSerializer):
    limit_events = EventSlugField(slug_field='slug', many=True)

    class Meta:
        model = Team
        fields = (
            'id', 'name', 'all_events', 'limit_events', 'can_create_events', 'can_change_teams',
            'can_change_organizer_settings', 'can_manage_gift_cards', 'can_change_event_settings',
            'can_change_items', 'can_view_orders', 'can_change_orders', 'can_view_vouchers',
            'can_change_vouchers', 'can_checkin_orders', 'can_manage_customers', 'can_manage_reusable_media'
        )

    def validate(self, data):
        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)
        if full_data.get('limit_events') and full_data.get('all_events'):
            raise ValidationError('Do not set both limit_events and all_events.')
        return data


class DeviceSerializer(serializers.ModelSerializer):
    limit_events = EventSlugField(slug_field='slug', many=True)
    device_id = serializers.IntegerField(read_only=True)
    unique_serial = serializers.CharField(read_only=True)
    hardware_brand = serializers.CharField(read_only=True)
    hardware_model = serializers.CharField(read_only=True)
    os_name = serializers.CharField(read_only=True)
    os_version = serializers.CharField(read_only=True)
    software_brand = serializers.CharField(read_only=True)
    software_version = serializers.CharField(read_only=True)
    created = serializers.DateTimeField(read_only=True)
    revoked = serializers.BooleanField(read_only=True)
    initialized = serializers.DateTimeField(read_only=True)
    initialization_token = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Device
        fields = (
            'device_id', 'unique_serial', 'initialization_token', 'all_events', 'limit_events',
            'revoked', 'name', 'created', 'initialized', 'hardware_brand', 'hardware_model',
            'os_name', 'os_version', 'software_brand', 'software_version', 'security_profile'
        )


class TeamInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamInvite
        fields = (
            'id', 'email'
        )

    def _send_invite(self, instance):
        try:
            mail(
                instance.email,
                _('pretix account invitation'),
                'pretixcontrol/email/invitation.txt',
                {
                    'user': self,
                    'organizer': self.context['organizer'].name,
                    'team': instance.team.name,
                    'url': build_global_uri('control:auth.invite', kwargs={
                        'token': instance.token
                    })
                },
                event=None,
                locale=get_language_without_region()  # TODO: expose?
            )
        except SendMailException:
            pass  # Already logged

    def create(self, validated_data):
        if 'email' in validated_data:
            try:
                user = User.objects.get(email__iexact=validated_data['email'])
            except User.DoesNotExist:
                if self.context['team'].invites.filter(email__iexact=validated_data['email']).exists():
                    raise ValidationError(_('This user already has been invited for this team.'))
                if 'native' not in get_auth_backends():
                    raise ValidationError('Users need to have a pretix account before they can be invited.')

                invite = self.context['team'].invites.create(email=validated_data['email'])
                self._send_invite(invite)
                invite.team.log_action(
                    'pretix.team.invite.created',
                    data={
                        'email': validated_data['email']
                    },
                    **self.context['log_kwargs']
                )
                return invite
            else:
                if self.context['team'].members.filter(pk=user.pk).exists():
                    raise ValidationError(_('This user already has permissions for this team.'))

                self.context['team'].members.add(user)
                self.context['team'].log_action(
                    'pretix.team.member.added',
                    data={
                        'email': user.email,
                        'user': user.pk,
                    },
                    **self.context['log_kwargs']
                )
                return TeamInvite(email=user.email)
        else:
            raise ValidationError('No email address given.')


class TeamAPITokenSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(default=True, read_only=True)

    class Meta:
        model = TeamAPIToken
        fields = (
            'id', 'name', 'active'
        )


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'email', 'fullname', 'require_2fa'
        )


class OrganizerSettingsSerializer(SettingsSerializer):
    default_fields = [
        'customer_accounts',
        'customer_accounts_native',
        'customer_accounts_link_by_email',
        'invoice_regenerate_allowed',
        'contact_mail',
        'imprint_url',
        'organizer_info_text',
        'event_list_type',
        'event_list_availability',
        'organizer_homepage_text',
        'organizer_link_back',
        'organizer_logo_image_large',
        'giftcard_length',
        'giftcard_expiry_years',
        'locales',
        'region',
        'event_team_provisioning',
        'primary_color',
        'theme_color_success',
        'theme_color_danger',
        'theme_color_background',
        'theme_round_borders',
        'primary_font',
        'organizer_logo_image_inherit',
        'organizer_logo_image',
        'privacy_url',
        'cookie_consent',
        'cookie_consent_dialog_title',
        'cookie_consent_dialog_text',
        'cookie_consent_dialog_text_secondary',
        'cookie_consent_dialog_button_yes',
        'cookie_consent_dialog_button_no',
        'reusable_media_active',
        'reusable_media_type_barcode',
        'reusable_media_type_barcode_identifier_length',
        'reusable_media_type_nfc_uid',
        'reusable_media_type_nfc_uid_autocreate_giftcard',
        'reusable_media_type_nfc_uid_autocreate_giftcard_currency',
        'reusable_media_type_nfc_mf0aes',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard_currency',
    ]

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)

    def validate(self, data):
        data = super().validate(data)
        settings_dict = self.instance.freeze()
        settings_dict.update(data)
        validate_organizer_settings(self.organizer, settings_dict)
        return data

    def get_new_filename(self, name: str) -> str:
        nonce = get_random_string(length=8)
        fname = '%s/%s.%s.%s' % (
            self.organizer.slug, name.split('/')[-1], nonce, name.split('.')[-1]
        )
        # TODO: make sure pub is always correct
        return 'pub/' + fname
