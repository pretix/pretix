import logging

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import ugettext as _

logger = logging.getLogger('pretix.presale.async')


class AsyncAction:
    task = None
    success_url = None
    error_url = None

    def do(self, *args):
        if settings.HAS_CELERY:
            from pretix.celery import app

            if hasattr(self.task, 'task') and isinstance(self.task.task, app.Task):
                return self._do_celery(args)
            else:
                raise TypeError('Method has no task attached')
        else:
            return self._do_sync(args)

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

    def _return_celery_result(self, res, timeout=.5):
        import celery.exceptions

        if not res.ready():
            try:
                res.get(timeout=timeout)
            except celery.exceptions.TimeoutError:
                pass
        ready = res.ready()
        data = {
            'async_id': res.id,
            'ready': ready
        }
        if ready:
            if res.successful() and not isinstance(res.info, Exception):
                smes = self.get_success_message(res.info)
                if smes:
                    messages.success(self.request, smes)
                # TODO: Do not store message if the ajax client stats that it will not redirect
                # but handle the mssage itself
                data.update({
                    'redirect': self.get_success_url(res.info),
                    'message': str(self.get_success_message(res.info))
                })
            else:
                messages.error(self.request, self.get_error_message(res.info))
                # TODO: Do not store message if the ajax client stats that it will not redirect
                # but handle the mssage itself
                data.update({
                    'redirect': self.get_error_url(),
                    'message': str(self.get_error_message(res.info))
                })
        return data

    def get_result(self, request):
        from celery.result import AsyncResult

        res = AsyncResult(request.GET.get('async_id'))
        if 'ajax' in self.request.GET:
            return JsonResponse(self._return_celery_result(res, timeout=0.25))
        else:
            if res.ready():
                if res.successful():
                    return self.success(res.info)
                else:
                    return self.error(res.info)
            return render(request, 'pretixpresale/waiting.html')

    def _do_celery(self, args):
        res = self.task.task.apply_async(args=args)
        if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
            data = self._return_celery_result(res)
            data['check_url'] = self.get_check_url(res.id, True)
            return JsonResponse(data)
        else:
            return redirect(self.get_check_url(res.id, False))

    def _do_sync(self, args):
        try:
            rs = getattr(self.__class__, 'task')(*args)
            return self.success(rs)
        except Exception as e:
            logger.exception('Error while executing task synchronously')
            return self.error(e)

    def success(self, value):
        smes = self.get_success_message(value)
        if smes:
            messages.success(self.request, smes)
        if "ajax" in self.request.POST or "ajax" in self.request.GET:
            return JsonResponse({
                'ready': True,
                'redirect': self.get_success_url(value),
                'message': str(self.get_success_message(value))
            })
        return redirect(self.get_success_url(value))

    def error(self, exception):
        messages.error(self.request, self.get_error_message(exception))
        if "ajax" in self.request.POST or "ajax" in self.request.GET:
            return JsonResponse({
                'ready': True,
                'redirect': self.get_error_url(),
                'message': str(self.get_error_message(exception))
            })
        return redirect(self.get_error_url())

    def get_error_message(self, exception):
        logger.error('Unexpected exception: %r' % exception)
        return _('An unexpected error has occured')

    def get_success_message(self, value):
        return _('The task has been completed')
