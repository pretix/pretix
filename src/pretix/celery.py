import os

from celery import Celery
from celery.utils.mail import ErrorMail

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")

from django.conf import settings

app = Celery('pretix')


class MyErrorMail(ErrorMail):

    def should_send(self, context, exc):
        from pretix.base.services.orders import OrderError
        from pretix.base.services.cart import CartError

        blacklist = (OrderError, CartError)
        return not isinstance(exc, blacklist)


app.config_from_object('django.conf:settings')
app.conf.CELERY_ANNOTATIONS = {
    '*': {
        'ErrorMail': MyErrorMail,
    }
}
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
