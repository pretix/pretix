import json

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _


class LogEntry(models.Model):
    """
    Represents a change or action that has been performed on another object
    in the database. This uses django.contrib.contenttypes to allow a
    relation to an arbitrary database object.

    :param datatime: The timestamp of the logged action
    :type datetime: datetime
    :param user: The user that performed the action
    :type user: User
    :param action_type: The type of action that has been performed. This is
       used to look up the renderer used to describe the action in a human-
       readable way. This should be some namespaced value using dotted
       notation to avoid duplicates, e.g.
       ``"pretix.plugins.banktransfer.incoming_transfer"``.
    :type action_type: str
    :param data: Arbitrary data that can be used by the log action renderer
    :type data: str
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    datetime = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey('User', null=True, blank=True, on_delete=models.PROTECT)
    event = models.ForeignKey('Event', null=True, blank=True, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=255)
    data = models.TextField(default='{}')

    class Meta:
        ordering = ('-datetime',)

    def display(self):
        from ..signals import logentry_display

        for receiver, response in logentry_display.send(self.event, logentry=self):
            if response:
                return response
        return self.action_type

    @cached_property
    def display_object(self):
        from . import Order, Voucher, Quota, Item, ItemCategory, Question, Event

        if self.content_type.model_class() is Event:
            return ''

        co = self.content_object
        a_map = None
        a_text = None

        if isinstance(co, Order):
            a_text = _('Order {val}')
            a_map = {
                'href': reverse('control:event.order', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'code': co.code
                }),
                'val': co.code,
            }
        elif isinstance(co, Voucher):
            a_text = _('Voucher {val}…')
            a_map = {
                'href': reverse('control:event.voucher', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'voucher': co.id
                }),
                'val': co.code[:6],
            }
        elif isinstance(co, Item):
            a_text = _('Product {val}')
            a_map = {
                'href': reverse('control:event.item', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'item': co.id
                }),
                'val': co.name,
            }
        elif isinstance(co, Quota):
            a_text = _('Quota {val}')
            a_map = {
                'href': reverse('control:event.items.quotas.show', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'quota': co.id
                }),
                'val': co.name,
            }
        elif isinstance(co, ItemCategory):
            a_text = _('Category {val}')
            a_map = {
                'href': reverse('control:event.items.categories.edit', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'category': co.id
                }),
                'val': co.name,
            }
        elif isinstance(co, Question):
            a_text = _('Question {val}')
            a_map = {
                'href': reverse('control:event.items.questions.show', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'question': co.id
                }),
                'val': co.question,
            }

        if a_text and a_map:
            a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
            return a_text.format_map(a_map)
        elif a_text:
            return a_text
        else:
            return ''

    @cached_property
    def parsed_data(self):
        return json.loads(self.data)

    def delete(self, using=None, keep_parents=False):
        raise TypeError("Logs cannot be deleted.")
