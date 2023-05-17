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
import base64
import logging

from cryptography.hazmat.backends.openssl.backend import Backend
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix import __version__
from pretix.api.auth.device import DeviceTokenAuthentication
from pretix.api.views.version import numeric_version
from pretix.base.models import CheckinList, Device, SubEvent
from pretix.base.models.devices import Gate, generate_api_token
from pretix.base.models.media import MediumKeySet
from pretix.base.services.media import get_keysets_for_organizer

logger = logging.getLogger(__name__)


class InitializationRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=190)
    hardware_brand = serializers.CharField(max_length=190)
    hardware_model = serializers.CharField(max_length=190)
    os_name = serializers.CharField(max_length=190, required=False, allow_null=True)
    os_version = serializers.CharField(max_length=190, required=False, allow_null=True)
    software_brand = serializers.CharField(max_length=190)
    software_version = serializers.CharField(max_length=190)
    info = serializers.JSONField(required=False, allow_null=True)
    rsa_pubkey = serializers.CharField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs.get('rsa_pubkey'):
            try:
                load_pem_public_key(
                    attrs['rsa_pubkey'].encode(), Backend()
                )
            except:
                raise ValidationError({'rsa_pubkey': ['Not a valid public key.']})
        return attrs


class UpdateRequestSerializer(serializers.Serializer):
    hardware_brand = serializers.CharField(max_length=190)
    hardware_model = serializers.CharField(max_length=190)
    os_name = serializers.CharField(max_length=190, required=False, allow_null=True)
    os_version = serializers.CharField(max_length=190, required=False, allow_null=True)
    software_brand = serializers.CharField(max_length=190)
    software_version = serializers.CharField(max_length=190)
    info = serializers.JSONField(required=False, allow_null=True)
    rsa_pubkey = serializers.CharField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs.get('rsa_pubkey'):
            try:
                load_pem_public_key(
                    attrs['rsa_pubkey'].encode(), Backend()
                )
            except:
                raise ValidationError({'rsa_pubkey': ['Not a valid public key.']})
        return attrs


class RSAEncryptedField(serializers.Field):
    def to_representation(self, value):
        public_key = load_pem_public_key(
            self.context['device'].rsa_pubkey.encode(), Backend()
        )
        cipher_text = public_key.encrypt(
            # RSA/ECB/PKCS1Padding
            value,
            padding.PKCS1v15()
        )
        return base64.b64encode(cipher_text).decode()


class MediumKeySetSerializer(serializers.ModelSerializer):
    uid_key = RSAEncryptedField(read_only=True)
    diversification_key = RSAEncryptedField(read_only=True)
    organizer = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    class Meta:
        model = MediumKeySet
        fields = [
            'public_id',
            'organizer',
            'active',
            'media_type',
            'uid_key',
            'diversification_key',
        ]


class GateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gate
        fields = [
            'id',
            'name',
            'identifier',
        ]


class DeviceSerializer(serializers.ModelSerializer):
    organizer = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    gate = GateSerializer(read_only=True)

    class Meta:
        model = Device
        fields = [
            'organizer', 'device_id', 'unique_serial', 'api_token',
            'name', 'security_profile', 'gate'
        ]


class InitializeView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, format=None):
        serializer = InitializationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            device = Device.objects.get(initialization_token=serializer.validated_data.get('token'))
        except Device.DoesNotExist:
            raise ValidationError({'token': ['Unknown initialization token.']})

        if device.initialized:
            raise ValidationError({'token': ['This initialization token has already been used.']})

        if device.revoked:
            raise ValidationError({'token': ['This initialization token has been revoked.']})

        device.initialized = now()
        device.hardware_brand = serializer.validated_data.get('hardware_brand')
        device.hardware_model = serializer.validated_data.get('hardware_model')
        device.os_name = serializer.validated_data.get('os_name')
        device.os_version = serializer.validated_data.get('os_version')
        device.software_brand = serializer.validated_data.get('software_brand')
        device.software_version = serializer.validated_data.get('software_version')
        device.info = serializer.validated_data.get('info')
        print(serializer.validated_data, request.data)
        device.rsa_pubkey = serializer.validated_data.get('rsa_pubkey')
        device.api_token = generate_api_token()
        device.save()

        device.log_action('pretix.device.initialized', data=serializer.validated_data, auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)


class UpdateView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    def post(self, request, format=None):
        serializer = UpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = request.auth
        device.hardware_brand = serializer.validated_data.get('hardware_brand')
        device.hardware_model = serializer.validated_data.get('hardware_model')
        device.os_name = serializer.validated_data.get('os_name')
        device.os_version = serializer.validated_data.get('os_version')
        device.software_brand = serializer.validated_data.get('software_brand')
        device.software_version = serializer.validated_data.get('software_version')
        if serializer.validated_data.get('rsa_pubkey') and serializer.validated_data.get('rsa_pubkey') != device.rsa_pubkey:
            if device.rsa_pubkey:
                raise ValidationError({'rsa_pubkey': ['You cannot change the rsa_pubkey of the device once it is set.']})
            else:
                device.rsa_pubkey = serializer.validated_data.get('rsa_pubkey')
        device.info = serializer.validated_data.get('info')
        device.save()
        device.log_action('pretix.device.updated', data=serializer.validated_data, auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)


class RollKeyView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    def post(self, request, format=None):
        device = request.auth
        device.api_token = generate_api_token()
        device.save()
        device.log_action('pretix.device.keyroll', auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)


class RevokeKeyView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    def post(self, request, format=None):
        device = request.auth
        device.revoked = True
        device.save()
        device.log_action('pretix.device.revoked', auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)


class InfoView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    def get(self, request, format=None):
        device = request.auth
        serializer = DeviceSerializer(device)
        return Response({
            'device': serializer.data,
            'server': {
                'version': {
                    'pretix': __version__,
                    'pretix_numeric': numeric_version(__version__),
                }
            },
            'medium_key_sets': MediumKeySetSerializer(
                get_keysets_for_organizer(device.organizer),
                many=True,
                context={'device': request.auth}
            ).data if device.rsa_pubkey else []
        })


class EventSelectionView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    @property
    def base_event_qs(self):
        qs = self.request.auth.get_events_with_any_permission().annotate(
            first_date=Coalesce('date_admission', 'date_from'),
            last_date=Coalesce('date_to', 'date_from'),
        ).filter(
            live=True,
            has_subevents=False
        ).order_by('first_date')
        if self.request.auth.gate:
            has_cl = CheckinList.objects.filter(
                event=OuterRef('pk'),
                gates__in=[self.request.auth.gate]
            )
            qs = qs.annotate(has_cl=Exists(has_cl)).filter(has_cl=True)
        return qs

    @property
    def base_subevent_qs(self):
        qs = SubEvent.objects.annotate(
            first_date=Coalesce('date_admission', 'date_from'),
            last_date=Coalesce('date_to', 'date_from'),
        ).filter(
            event__organizer=self.request.auth.organizer,
            event__live=True,
            event__in=self.request.auth.get_events_with_any_permission(),
            active=True,
        ).select_related('event').order_by('first_date')
        if self.request.auth.gate:
            has_cl = CheckinList.objects.filter(
                Q(subevent__isnull=True) | Q(subevent=OuterRef('pk')),
                event_id=OuterRef('event_id'),
                gates__in=[self.request.auth.gate]
            )
            qs = qs.annotate(has_cl=Exists(has_cl)).filter(has_cl=True)
        return qs

    def _max_first_date_event(self, a, b):
        if a and b:
            return a if a.first_date > b.first_date else b
        return a or b

    def _min_first_date_event(self, a, b):
        if a and b:
            return a if a.first_date < b.first_date else b
        return a or b

    def get(self, request, format=None):
        device = request.auth
        current_event = None
        current_subevent = None
        if 'current_event' in request.query_params:
            current_event = device.organizer.events.filter(slug=request.query_params['current_event']).first()
            if current_event and 'current_subevent' in request.query_params:
                current_subevent = current_event.subevents.filter(pk=request.query_params['current_subevent']).first()
            if current_event and current_event.has_subevents and not current_subevent:
                current_event = None

        if current_event:
            current_ev = current_subevent or current_event
        else:
            current_ev = None

        # The event that is selected might not currently be running. We cannot rely on all events having a proper end date.
        # Also, if events run back-to-back, the later event can overlap the earlier event due to its admission-time.
        # In any case, we'll need to decide between the current event, the event that last started (and might still be running) and the
        # event that starts next (and might already be letting people in), so let's get these as well!
        # No matter if current event is given in query_params, always check whether another event already
        # started – overlaps can happen through e.g. admission-time overlapping or misconfig).
        # Note that last_started here means either admission started or the event itself started.
        last_started_ev = self._max_first_date_event(
            self.base_event_qs.filter(first_date__lte=now()).last(),
            self.base_subevent_qs.filter(first_date__lte=now()).last()
        )
        if last_started_ev and current_ev != last_started_ev and \
           last_started_ev.date_to and now() < last_started_ev.date_to:
            return self._suggest_event(current_event, last_started_ev)

        if current_event:
            current_ev_start = current_ev.date_admission or current_ev.date_from
            tz = current_event.timezone
            if current_ev.date_to and current_ev_start <= now() < current_ev.date_to:
                # The event that is selected is currently running. Good enough.
                return Response(status=status.HTTP_304_NOT_MODIFIED)

        upcoming_ev = self._min_first_date_event(
            self.base_event_qs.filter(first_date__gt=now()).first(),
            self.base_subevent_qs.filter(first_date__gt=now()).first()
        )

        if not upcoming_ev and not last_started_ev:
            # Ooops, no events here
            return Response(status=status.HTTP_404_NOT_FOUND)
        elif upcoming_ev and not last_started_ev:
            # No event running, so let's take the next one
            return self._suggest_event(current_event, upcoming_ev)
        elif last_started_ev and not upcoming_ev:
            # No event upcoming, so let's take the next one
            return self._suggest_event(current_event, last_started_ev)

        if not current_event:
            tz = (upcoming_ev or last_started_ev).timezone

        lse_d = last_started_ev.date_from.astimezone(tz).date()
        upc_d = upcoming_ev.date_from.astimezone(tz).date()
        now_d = now().astimezone(tz).date()
        if lse_d == now_d and upc_d != now_d:
            # Last event was today, next is tomorrow, stick with today
            return self._suggest_event(current_event, last_started_ev)
        elif lse_d != now_d and upc_d == now_d:
            # Last event was yesterday, next is today, stick with today
            return self._suggest_event(current_event, upcoming_ev)

        # Both last and next event are today, we switch over in the middle
        if now() > last_started_ev.last_date + (upcoming_ev.first_date - last_started_ev.last_date) / 2:
            return self._suggest_event(current_event, upcoming_ev)
        else:
            return self._suggest_event(current_event, last_started_ev)

    def _suggest_event(self, current_event, ev):
        current_checkinlist = None
        if current_event and 'current_checkinlist' in self.request.query_params:
            current_checkinlist = current_event.checkin_lists.filter(
                pk=self.request.query_params['current_checkinlist']
            ).first()
        if isinstance(ev, SubEvent):
            checkinlist_qs = ev.event.checkin_lists.filter(Q(subevent__isnull=True) | Q(subevent=ev))
        else:
            checkinlist_qs = ev.checkin_lists

        if self.request.auth.gate:
            checkinlist_qs = checkinlist_qs.filter(gates__in=[self.request.auth.gate])

        checkinlist = None
        if current_checkinlist:
            checkinlist = checkinlist_qs.filter(Q(name=current_checkinlist.name) | Q(pk=current_checkinlist.pk)).first()
        if not checkinlist:
            checkinlist = checkinlist_qs.first()
        r = {
            'event': {
                'slug': ev.event.slug if isinstance(ev, SubEvent) else ev.slug,
                'name': str(ev.event.name) if isinstance(ev, SubEvent) else str(ev.name),
            },
            'subevent': ev.pk if isinstance(ev, SubEvent) else None,
            'checkinlist': checkinlist.pk if checkinlist else None,
        }

        if r == {
            'event': {
                'slug': current_event.slug if current_event else None,
                'name': str(current_event.name) if current_event else None,
            },
            'subevent': (
                int(self.request.query_params.get('current_subevent'))
                if self.request.query_params.get('current_subevent') else None
            ),
            'checkinlist': (
                int(self.request.query_params.get('current_checkinlist'))
                if self.request.query_params.get('current_checkinlist') else None
            ),
        }:
            return Response(status=status.HTTP_304_NOT_MODIFIED)
        return Response(r)
