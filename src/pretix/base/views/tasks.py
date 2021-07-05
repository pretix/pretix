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
from importlib import import_module

import celery.exceptions
import pytz
from celery import states
from celery.result import AsyncResult
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse, QueryDict
from django.shortcuts import redirect, render
from django.test import RequestFactory
from django.utils import timezone, translation
from django.utils.timezone import get_current_timezone
from django.utils.translation import get_language, gettext as _
from django.views.generic import FormView

from pretix.base.models import User
from pretix.base.services.tasks import ProfiledEventTask
from pretix.celery_app import app

logger = logging.getLogger('pretix.base.tasks')


class AsyncMixin:
    success_url = None
    error_url = None
    known_errortypes = []

    def get_success_url(self, value):
        return self.success_url

    def get_error_url(self):
        return self.error_url

    def get_check_url(self, task_id, ajax):
        return self.request.path + '?async_id=%s' % task_id + ('&ajax=1' if ajax else '')

    def _ajax_response_data(self):
        return {}

    def _return_ajax_result(self, res, timeout=.5):
        ready = res.ready()
        if not ready:
            try:
                res.get(timeout=timeout, propagate=False)
            except celery.exceptions.TimeoutError:
                pass
            except ConnectionError:
                # Redis probably just restarted, let's just report not ready and retry next time
                data = self._ajax_response_data()
                data.update({
                    'async_id': res.id,
                    'ready': False
                })
                return data

        state, info = res.state, res.info
        data = self._ajax_response_data()
        data.update({
            'async_id': res.id,
            'ready': ready,
            'started': False,
        })
        if ready:
            if state == states.SUCCESS and not isinstance(info, Exception):
                smes = self.get_success_message(info)
                if smes:
                    messages.success(self.request, smes)
                # TODO: Do not store message if the ajax client states that it will not redirect
                # but handle the message itself
                data.update({
                    'redirect': self.get_success_url(info),
                    'success': True,
                    'message': str(self.get_success_message(info))
                })
            else:
                messages.error(self.request, self.get_error_message(info))
                # TODO: Do not store message if the ajax client states that it will not redirect
                # but handle the message itself
                data.update({
                    'redirect': self.get_error_url(),
                    'success': False,
                    'message': str(self.get_error_message(info))
                })
        elif state == 'PROGRESS':
            data.update({
                'started': True,
                'percentage': info.get('value', 0) if isinstance(info, dict) else 0
            })
        elif state == 'STARTED':
            data.update({
                'started': True,
            })
        return data

    def get_result(self, request):
        res = AsyncResult(request.GET.get('async_id'))
        if 'ajax' in self.request.GET:
            return JsonResponse(self._return_ajax_result(res, timeout=0.25))
        else:
            if res.ready():
                if res.successful() and not isinstance(res.info, Exception):
                    return self.success(res.info)
                else:
                    return self.error(res.info)
            return render(request, 'pretixpresale/waiting.html')

    def success(self, value):
        smes = self.get_success_message(value)
        if smes:
            messages.success(self.request, smes)
        if "ajax" in self.request.POST or "ajax" in self.request.GET:
            return JsonResponse({
                'ready': True,
                'success': True,
                'redirect': self.get_success_url(value),
                'message': str(self.get_success_message(value))
            })
        return redirect(self.get_success_url(value))

    def error(self, exception):
        messages.error(self.request, self.get_error_message(exception))
        if "ajax" in self.request.POST or "ajax" in self.request.GET:
            return JsonResponse({
                'ready': True,
                'success': False,
                'redirect': self.get_error_url(),
                'message': str(self.get_error_message(exception))
            })
        return redirect(self.get_error_url())

    def get_error_message(self, exception):
        if isinstance(exception, dict) and exception['exc_type'] in self.known_errortypes:
            return exception['exc_message']
        elif exception.__class__.__name__ in self.known_errortypes:
            return str(exception)
        else:
            logger.error('Unexpected exception: %r' % exception)
            return _('An unexpected error has occurred, please try again later.')

    def get_success_message(self, value):
        return _('The task has been completed.')


class AsyncAction(AsyncMixin):
    task = None

    def do(self, *args, **kwargs):
        if not isinstance(self.task, app.Task):
            raise TypeError('Method has no task attached')

        try:
            res = self.task.apply_async(args=args, kwargs=kwargs)
        except ConnectionError:
            # Task very likely not yet sent, due to redis restarting etc. Let's try once again
            res = self.task.apply_async(args=args, kwargs=kwargs)

        if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
            data = self._return_ajax_result(res)
            data['check_url'] = self.get_check_url(res.id, True)
            return JsonResponse(data)
        else:
            if res.ready():
                if res.successful() and not isinstance(res.info, Exception):
                    return self.success(res.info)
                else:
                    return self.error(res.info)
            return redirect(self.get_check_url(res.id, False))

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return self.http_method_not_allowed(request)


class AsyncFormView(AsyncMixin, FormView):
    """
    FormView variant in which instead of ``form_valid``, an ``async_form_valid``
    is executed in a celery task. Note that this places some severe limitations
    on the form and the view, e.g. neither ``get_form*`` nor the form itself
    may depend on the request object unless specifically supported by this class.
    Also, all form keyword arguments except ``instance`` need to be serializable.
    """
    known_errortypes = ['ValidationError']

    def __init_subclass__(cls):
        def async_execute(self, *, request_path, query_string, form_kwargs, locale, tz, organizer=None, event=None, user=None, session_key=None):
            view_instance = cls()
            form_kwargs['data'] = QueryDict(form_kwargs['data'])
            req = RequestFactory().post(
                request_path + '?' + query_string,
                data=form_kwargs['data'].urlencode(),
                content_type='application/x-www-form-urlencoded'
            )
            view_instance.request = req
            if event:
                view_instance.request.event = event
                view_instance.request.organizer = event.organizer
            elif organizer:
                view_instance.request.organizer = organizer
            if user:
                view_instance.request.user = User.objects.get(pk=user)
            if session_key:
                engine = import_module(settings.SESSION_ENGINE)
                self.SessionStore = engine.SessionStore
                view_instance.request.session = self.SessionStore(session_key)

            with translation.override(locale), timezone.override(pytz.timezone(tz)):
                form_class = view_instance.get_form_class()
                if form_kwargs.get('instance'):
                    cls.model.objects.get(pk=form_kwargs['instance'])

                form_kwargs = view_instance.get_async_form_kwargs(form_kwargs, organizer, event)
                form = form_class(**form_kwargs)
                form.is_valid()
                return view_instance.async_form_valid(self, form)

        cls.async_execute = app.task(
            base=ProfiledEventTask,
            bind=True,
            name=cls.__module__ + '.' + cls.__name__ + '.async_execute',
            throws=(ValidationError,)
        )(async_execute)

    def async_form_valid(self, task, form):
        pass

    def get_async_form_kwargs(self, form_kwargs, organizer=None, event=None):
        return form_kwargs

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.files:
            raise TypeError('File upload currently not supported in AsyncFormView')
        form_kwargs = {
            k: v for k, v in self.get_form_kwargs().items()
        }
        if form_kwargs.get('instance'):
            if form_kwargs['instance'].pk:
                form_kwargs['instance'] = form_kwargs['instance'].pk
            else:
                form_kwargs['instance'] = None
        form_kwargs.setdefault('data', QueryDict())
        form_kwargs['data'] = form_kwargs['data'].urlencode()
        form_kwargs['initial'] = {}
        form_kwargs.pop('event', None)
        kwargs = {
            'request_path': self.request.path,
            'query_string': self.request.GET.urlencode(),
            'form_kwargs': form_kwargs,
            'locale': get_language(),
            'tz': get_current_timezone().zone,
        }
        if hasattr(self.request, 'organizer'):
            kwargs['organizer'] = self.request.organizer.pk
        if self.request.user.is_authenticated:
            kwargs['user'] = self.request.user.pk
        if hasattr(self.request, 'event'):
            kwargs['event'] = self.request.event.pk
        if hasattr(self.request, 'session'):
            kwargs['session_key'] = self.request.session.session_key

        try:
            res = type(self).async_execute.apply_async(kwargs=kwargs)
        except ConnectionError:
            # Task very likely not yet sent, due to redis restarting etc. Let's try once again
            res = type(self).async_execute.apply_async(kwargs=kwargs)

        if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
            data = self._return_ajax_result(res)
            data['check_url'] = self.get_check_url(res.id, True)
            return JsonResponse(data)
        else:
            if res.ready():
                if res.successful() and not isinstance(res.info, Exception):
                    return self.success(res.info)
                else:
                    return self.error(res.info)
            return redirect(self.get_check_url(res.id, False))
