import logging

from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix.api.auth.device import DeviceTokenAuthentication
from pretix.base.models import Device, SubEvent
from pretix.base.models.devices import Gate, generate_api_token

logger = logging.getLogger(__name__)


class InitializationRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=190)
    hardware_brand = serializers.CharField(max_length=190)
    hardware_model = serializers.CharField(max_length=190)
    software_brand = serializers.CharField(max_length=190)
    software_version = serializers.CharField(max_length=190)


class UpdateRequestSerializer(serializers.Serializer):
    hardware_brand = serializers.CharField(max_length=190)
    hardware_model = serializers.CharField(max_length=190)
    software_brand = serializers.CharField(max_length=190)
    software_version = serializers.CharField(max_length=190)


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
    authentication_classes = tuple()
    permission_classes = tuple()

    def post(self, request, format=None):
        serializer = InitializationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            device = Device.objects.get(initialization_token=serializer.validated_data.get('token'))
        except Device.DoesNotExist:
            raise ValidationError({'token': ['Unknown initialization token.']})

        if device.initialized:
            raise ValidationError({'token': ['This initialization token has already been used.']})

        device.initialized = now()
        device.hardware_brand = serializer.validated_data.get('hardware_brand')
        device.hardware_model = serializer.validated_data.get('hardware_model')
        device.software_brand = serializer.validated_data.get('software_brand')
        device.software_version = serializer.validated_data.get('software_version')
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
        device.software_brand = serializer.validated_data.get('software_brand')
        device.software_version = serializer.validated_data.get('software_version')
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


class EventSelectionView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    @property
    def base_event_qs(self):
        return self.request.auth.organizer.events.annotate(
            first_date=Coalesce('date_admission', 'date_from'),
            last_date=Coalesce('date_to', 'date_from'),
        ).filter(
            live=True,
            has_subevents=False
        ).order_by('first_date')

    @property
    def base_subevent_qs(self):
        return SubEvent.objects.annotate(
            first_date=Coalesce('date_admission', 'date_from'),
            last_date=Coalesce('date_to', 'date_from'),
        ).filter(
            event__organizer=self.request.auth.organizer,
            event__live=True,
            active=True,
        ).select_related('event').order_by('first_date')

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
            current_ev_start = current_ev.date_admission or current_ev.date_from
            tz = current_event.timezone
            if current_ev.date_to and current_ev_start < now() < current_ev.date_to:
                # The event that is selected is currently running. Good enough.
                return Response(status=status.HTTP_304_NOT_MODIFIED)

        # The event that is selected is not currently running. We cannot rely on all events having a proper end date.
        # In any case, we'll need to decide between the event that last started (and might still be running) and the
        # event that starts next (and might already be letting people in), so let's get these two!
        last_started_ev = self.base_event_qs.filter(first_date__lte=now()).last() or self.base_subevent_qs.filter(
            first_date__lte=now()).last()

        upcoming_event = self.base_event_qs.filter(first_date__gt=now()).first()
        upcoming_subevent = self.base_subevent_qs.filter(first_date__gt=now()).first()
        if upcoming_event and upcoming_subevent:
            if upcoming_event.first_date > upcoming_subevent.first_date:
                upcoming_ev = upcoming_subevent
            else:
                upcoming_ev = upcoming_event
        else:
            upcoming_ev = upcoming_event or upcoming_subevent

        if not upcoming_ev and not last_started_ev:
            # Ooops, no events here
            return Response(status=status.HTTP_404_NOT_FOUND)
        elif upcoming_ev and not last_started_ev:
            # No event running, so let's take the next one
            return self._suggest_event(current_event, upcoming_ev)
        elif last_started_ev and not upcoming_ev:
            # No event upcoming, so let's take the next one
            return self._suggest_event(current_event, last_started_ev)

        if last_started_ev.date_to and now() < last_started_ev.date_to:
            # The event that last started is currently running. Good enough.
            return self._suggest_event(current_event, last_started_ev)

        if not current_event:
            tz = (upcoming_event or last_started_ev).timezone

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
