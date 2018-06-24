from collections import OrderedDict

from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nFormField, I18nTextarea, I18nTextInput
from i18nfield.strings import LazyI18nString

from pretix.base.forms import PlaceholderValidator
from pretix.base.payment import BasePaymentProvider
from pretix.base.templatetags.money import money_filter
from pretix.base.templatetags.rich_text import rich_text


class ManualPayment(BasePaymentProvider):
    identifier = 'manual'
    verbose_name = _('Manual payment')

    @property
    def public_name(self):
        return str(self.settings.get('public_name', as_type=LazyI18nString))

    @property
    def settings_form_fields(self):
        d = OrderedDict(
            [
                ('public_name', I18nFormField(
                    label=_('Payment method name'),
                    widget=I18nTextInput,
                )),
                ('checkout_description', I18nFormField(
                    label=_('Payment process description during checkout'),
                    help_text=_('This text will be shown during checkout when the user selects this payment method. '
                                'It should give a short explanation on this payment method.'),
                    widget=I18nTextarea,
                )),
                ('email_instructions', I18nFormField(
                    label=_('Payment process description in order confirmation emails'),
                    help_text=_('This text will be included for the {payment_info} placeholder in order confirmation '
                                'mails. It should instruct the user on how to proceed with the payment. You can use'
                                'the placeholders {order}, {total}, {currency} and {total_with_currency}'),
                    widget=I18nTextarea,
                    validators=[PlaceholderValidator(['{order}', '{total}', '{currency}', '{total_with_currency}'])],
                )),
                ('pending_description', I18nFormField(
                    label=_('Payment process description for pending orders'),
                    help_text=_('This text will be shown on the order confirmation page for pending orders. '
                                'It should instruct the user on how to proceed with the payment. You can use'
                                'the placeholders {order}, {total}, {currency} and {total_with_currency}'),
                    widget=I18nTextarea,
                    validators=[PlaceholderValidator(['{order}', '{total}', '{currency}', '{total_with_currency}'])],
                )),
            ] + list(super().settings_form_fields.items())
        )
        d.move_to_end('_enabled', last=False)
        return d

    def payment_form_render(self, request) -> str:
        return rich_text(
            str(self.settings.get('checkout_description', as_type=LazyI18nString))
        )

    def checkout_prepare(self, request, total):
        return True

    def payment_is_valid_session(self, request):
        return True

    def checkout_confirm_render(self, request):
        return self.payment_form_render(request)

    def format_map(self, order):
        return {
            'order': order.code,
            'total': order.total,
            'currency': self.event.currency,
            'total_with_currency': money_filter(order.total, self.event.currency)
        }

    def order_pending_mail_render(self, order) -> str:
        msg = str(self.settings.get('email_instructions', as_type=LazyI18nString)).format_map(self.format_map(order))
        return msg

    def order_pending_render(self, request, order) -> str:
        return rich_text(
            str(self.settings.get('pending_description', as_type=LazyI18nString)).format_map(self.format_map(order))
        )

    def order_control_render(self, request, order) -> str:
        template = get_template('pretixplugins/manualpayment/control.html')
        ctx = {'request': request, 'event': self.event,
               'order': order}
        return template.render(ctx)
