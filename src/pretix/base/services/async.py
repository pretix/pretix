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

from pretix.celery_app import app


class ProfiledTask(app.Task):

    def __call__(self, *args, **kwargs):

        if settings.PROFILING_RATE > 0 and random.random() < settings.PROFILING_RATE / 100:
            profiler = cProfile.Profile()
            profiler.enable()
            starttime = time.time()
            ret = super().__call__(*args, **kwargs)
            profiler.disable()
            tottime = time.time() - starttime
            profiler.dump_stats(os.path.join(settings.PROFILE_DIR, '{time:.0f}_{tottime:.3f}_celery_{t}.pstat'.format(
                t=self.name, tottime=tottime, time=time.time()
            )))
            return ret
        else:
            return super().__call__(*args, **kwargs)


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
