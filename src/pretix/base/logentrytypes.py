from collections import defaultdict

from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.signals import EventPluginRegistry


def make_link(a_map, wrapper, is_active=True, event=None, plugin_name=None):
    if a_map:
        if is_active:
            a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
        elif event and plugin_name:
            a_map['val'] = (
                '<i>{val}</i> <a href="{plugin_href}">'
                '<span data-toggle="tooltip" title="{errmes}" class="fa fa-warning fa-fw"></span></a>'
            ).format_map({
                **a_map,
                "errmes": _("The relevant plugin is currently not active. To activate it, click here to go to the plugin settings."),
                "plugin_href": reverse('control:event.settings.plugins', kwargs={
                    'organizer': event.organizer.slug,
                    'event': event.slug,
                }) + '#plugin_' + plugin_name,
            })
        else:
            a_map['val'] = '<i>{val}</i> <span data-toggle="tooltip" title="{errmes}" class="fa fa-warning fa-fw"></span>'.format_map({
                **a_map,
                "errmes": _("The relevant plugin is currently not active."),
            })
        return wrapper.format_map(a_map)


class LogEntryTypeRegistry(EventPluginRegistry):
    def new_from_dict(self, data):
        def reg(clz):
            for action_type, plain in data.items():
                self.register(clz(action_type=action_type, plain=plain))
        return reg


log_entry_types = LogEntryTypeRegistry({'action_type': lambda o: getattr(o, 'action_type')})


class LogEntryType:
    def __init__(self, action_type=None, plain=None):
        assert self.__module__ != LogEntryType.__module__  # must not instantiate base classes, only derived ones
        if action_type:
            self.action_type = action_type
        if plain:
            self.plain = plain

    def display(self, logentry):
        if hasattr(self, 'plain'):
            plain = str(self.plain)
            if '{' in plain:
                data = defaultdict(lambda: '?', logentry.parsed_data)
                return plain.format_map(data)
            else:
                return plain

    def get_object_link_info(self, logentry) -> dict:
        pass

    def get_object_link(self, logentry):
        a_map = self.get_object_link_info(logentry)
        return make_link(a_map, self.object_link_wrapper)

    object_link_wrapper = '{val}'

    def shred_pii(self, logentry):
        raise NotImplementedError


class EventLogEntryType(LogEntryType):
    def get_object_link_info(self, logentry) -> dict:
        if hasattr(self, 'object_link_viewname') and hasattr(self, 'object_link_argname') and logentry.content_object:
            return {
                'href': reverse(self.object_link_viewname, kwargs={
                    'event': logentry.event.slug,
                    'organizer': logentry.event.organizer.slug,
                    self.object_link_argname: self.object_link_argvalue(logentry.content_object),
                }),
                'val': escape(self.object_link_display_name(logentry.content_object)),
            }

    def object_link_argvalue(self, content_object):
        return content_object.id

    def object_link_display_name(self, content_object):
        return str(content_object)


class OrderLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Order {val}')
    object_link_viewname = 'control:event.order'
    object_link_argname = 'code'

    def object_link_argvalue(self, order):
        return order.code

    def object_link_display_name(self, order):
        return order.code


class VoucherLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Voucher {val}…')
    object_link_viewname = 'control:event.voucher'
    object_link_argname = 'voucher'

    def object_link_display_name(self, order):
        return order.code[:6]


class ItemLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Product {val}')
    object_link_viewname = 'control:event.item'
    object_link_argname = 'item'


class SubEventLogEntryType(EventLogEntryType):
    object_link_wrapper = pgettext_lazy('subevent', 'Date {val}')
    object_link_viewname = 'control:event.subevent'
    object_link_argname = 'subevent'


class QuotaLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Quota {val}')
    object_link_viewname = 'control:event.items.quotas.show'
    object_link_argname = 'quota'


class DiscountLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Discount {val}')
    object_link_viewname = 'control:event.items.discounts.edit'
    object_link_argname = 'discount'


class ItemCategoryLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Category {val}')
    object_link_viewname = 'control:event.items.categories.edit'
    object_link_argname = 'category'


class QuestionLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Question {val}')
    object_link_viewname = 'control:event.items.questions.show'
    object_link_argname = 'question'


class TaxRuleLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Tax rule {val}')
    object_link_viewname = 'control:event.settings.tax.edit'
    object_link_argname = 'rule'


class NoOpShredderMixin:
    def shred_pii(self, logentry):
        pass


class ClearDataShredderMixin:
    def shred_pii(self, logentry):
        logentry.data = None
