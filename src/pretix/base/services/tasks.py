"""
This code has been taken from
https://blog.hypertrack.io/2016/10/08/dealing-with-database-transactions-in-django-celery/

Usage:
    from pretix.base.services.async import TransactionAwareTask
    @task(base=TransactionAwareTask)
    def task_…():
"""
import cProfile
import os
import random
import time

from django.conf import settings
from django.db import transaction
from django_scopes import scope, scopes_disabled

from pretix.base.metrics import (
    pretix_task_duration_seconds, pretix_task_runs_total,
)
from pretix.base.models import Event, Organizer, User
from pretix.celery_app import app


class ProfiledTask(app.Task):
    def __call__(self, *args, **kwargs):

        if settings.PROFILING_RATE > 0 and random.random() < settings.PROFILING_RATE / 100:
            profiler = cProfile.Profile()
            profiler.enable()
            t0 = time.perf_counter()
            ret = super().__call__(*args, **kwargs)
            tottime = time.perf_counter() - t0
            profiler.disable()
            profiler.dump_stats(os.path.join(settings.PROFILE_DIR, '{time:.0f}_{tottime:.3f}_celery_{t}.pstat'.format(
                t=self.name, tottime=tottime, time=time.time()
            )))
        else:
            t0 = time.perf_counter()
            ret = super().__call__(*args, **kwargs)
            tottime = time.perf_counter() - t0

        if settings.METRICS_ENABLED:
            pretix_task_duration_seconds.observe(tottime, task_name=self.name)
        return ret

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if settings.METRICS_ENABLED:
            expected = False
            for t in self.throws:
                if isinstance(exc, t):
                    expected = True
                    break
            pretix_task_runs_total.inc(1, task_name=self.name, status="expected-error" if expected else "error")

        return super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        if settings.METRICS_ENABLED:
            pretix_task_runs_total.inc(1, task_name=self.name, status="success")

        return super().on_success(retval, task_id, args, kwargs)


class EventTask(app.Task):
    def __call__(self, *args, **kwargs):
        if 'event_id' in kwargs:
            event_id = kwargs.get('event_id')
            with scopes_disabled():
                event = Event.objects.select_related('organizer').get(pk=event_id)
            del kwargs['event_id']
            kwargs['event'] = event
        elif 'event' in kwargs:
            event_id = kwargs.get('event')
            with scopes_disabled():
                event = Event.objects.select_related('organizer').get(pk=event_id)
            kwargs['event'] = event
        else:
            args = list(args)
            event_id = args[0]
            with scopes_disabled():
                event = Event.objects.select_related('organizer').get(pk=event_id)
            args[0] = event

        with scope(organizer=event.organizer):
            ret = super().__call__(*args, **kwargs)
        return ret


class OrganizerUserTask(app.Task):
    def __call__(self, *args, **kwargs):
        if 'organizer_id' in kwargs:
            organizer_id = kwargs.get('organizer_id')
            with scopes_disabled():
                organizer = Organizer.objects.get(pk=organizer_id)
            del kwargs['organizer_id']
            kwargs['organizer'] = organizer
        elif 'organizer' in kwargs:
            organizer_id = kwargs.get('organizer')
            with scopes_disabled():
                organizer = Organizer.objects.get(pk=organizer_id)
            kwargs['organizer'] = organizer
        else:
            args = list(args)
            organizer_id = args[0]
            with scopes_disabled():
                organizer = Organizer.objects.get(pk=organizer_id)
            args[0] = organizer

        if 'user_id' in kwargs:
            user_id = kwargs.get('user_id')
            with scopes_disabled():
                user = User.objects.get(pk=user_id)
            del kwargs['user_id']
            kwargs['user'] = user
        elif 'user' in kwargs:
            user_id = kwargs.get('user')
            with scopes_disabled():
                user = User.objects.get(pk=user_id)
            kwargs['user'] = user
        else:
            args = list(args)
            user_id = args[1]
            with scopes_disabled():
                user = User.objects.get(pk=user_id)
            args[1] = user

        with scope(organizer=organizer):
            ret = super().__call__(*args, **kwargs)
        return ret


class ProfiledEventTask(ProfiledTask, EventTask):
    pass


class ProfiledOrganizerUserTask(ProfiledTask, OrganizerUserTask):
    pass


class TransactionAwareTask(ProfiledTask):
    """
    Task class which is aware of django db transactions and only executes tasks
    after transaction has been committed
    """

    def apply_async(self, *args, **kwargs):
        """
        Unlike the default task in celery, this task does not return an async
        result
        """
        transaction.on_commit(
            lambda: super(TransactionAwareTask, self).apply_async(*args, **kwargs)
        )


class TransactionAwareProfiledEventTask(ProfiledEventTask):

    def apply_async(self, *args, **kwargs):
        """
        Unlike the default task in celery, this task does not return an async
        result
        """
        transaction.on_commit(
            lambda: super(TransactionAwareProfiledEventTask, self).apply_async(*args, **kwargs)
        )
