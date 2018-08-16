import logging

import celery.exceptions
from celery.result import AsyncResult
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import ugettext as _

from pretix.celery_app import app

logger = logging.getLogger('pretix.base.tasks')


class AsyncAction:
    task = None
    success_url = None
    error_url = None
    known_errortypes = []

    def do(self, *args, **kwargs):
        if not isinstance(self.task, app.Task):
            raise TypeError('Method has no task attached')

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

    def get_success_url(self, value):
        return self.success_url

    def get_error_url(self):
        return self.error_url

    def get_check_url(self, task_id, ajax):
        return self.request.path + '?async_id=%s' % task_id + ('&ajax=1' if ajax else '')

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return self.http_method_not_allowed(request)

    def _ajax_response_data(self):
        return {}

    def _return_ajax_result(self, res, timeout=.5):
        if not res.ready():
            try:
                res.get(timeout=timeout, propagate=False)
            except celery.exceptions.TimeoutError:
                pass

        ready = res.ready()
        data = self._ajax_response_data()
        data.update({
            'async_id': res.id,
            'ready': ready
        })
        if ready:
            if res.successful() and not isinstance(res.info, Exception):
                smes = self.get_success_message(res.info)
                if smes:
                    messages.success(self.request, smes)
                # TODO: Do not store message if the ajax client states that it will not redirect
                # but handle the mssage itself
                data.update({
                    'redirect': self.get_success_url(res.info),
                    'success': True,
                    'message': str(self.get_success_message(res.info))
                })
            else:
                messages.error(self.request, self.get_error_message(res.info))
                # TODO: Do not store message if the ajax client states that it will not redirect
                # but handle the mssage itself
                data.update({
                    'redirect': self.get_error_url(),
                    'success': False,
                    'message': str(self.get_error_message(res.info))
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
            return _('An unexpected error has occurred.')

    def get_success_message(self, value):
        return _('The task has been completed.')
