from itertools import chain

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.utils.encoding import force_text
from django.utils.formats import number_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms.questions import (
    BaseInvoiceAddressForm, BaseQuestionsForm,
)
from pretix.base.models import ItemVariation
from pretix.base.models.tax import TAXED_ZERO
from pretix.base.templatetags.money import money_filter
from pretix.base.templatetags.rich_text import rich_text
from pretix.base.validators import EmailBlacklistValidator
from pretix.presale.signals import contact_form_fields


class ContactForm(forms.Form):
    required_css_class = 'required'
    email = forms.EmailField(label=_('E-mail'),
                             help_text=_('Make sure to enter a valid email address. We will send you an order '
                                         'confirmation including a link that you need to access your order later.'),
                             validators=[EmailBlacklistValidator()],
                             )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        if self.event.settings.order_email_asked_twice:
            self.fields['email_repeat'] = forms.EmailField(
                label=_('E-mail address (repeated)'),
                help_text=_('Please enter the same email address again to make sure you typed it correctly.')
            )

        if not self.request.session.get('iframe_session', False):
            # There is a browser quirk in Chrome that leads to incorrect initial scrolling in iframes if there
            # is an autofocus field. Who would have thought… See e.g. here:
            # https://floatboxjs.com/forum/topic.php?post=8440&usebb_sid=2e116486a9ec6b7070e045aea8cded5b#post8440
            self.fields['email'].widget.attrs['autofocus'] = 'autofocus'

        responses = contact_form_fields.send(self.event, request=self.request)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value

    def clean(self):
        if self.event.settings.order_email_asked_twice and self.cleaned_data.get('email') and self.cleaned_data.get('email_repeat'):
            if self.cleaned_data.get('email').lower() != self.cleaned_data.get('email_repeat').lower():
                raise ValidationError(_('Please enter the same email address twice.'))


class InvoiceAddressForm(BaseInvoiceAddressForm):
    required_css_class = 'required'
    vat_warning = True


class InvoiceNameForm(InvoiceAddressForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in list(self.fields.keys()):
            if f != 'name_parts':
                del self.fields[f]


class QuestionsForm(BaseQuestionsForm):
    """
    This form class is responsible for asking order-related questions. This includes
    the attendee name for admission tickets, if the corresponding setting is enabled,
    as well as additional questions defined by the organizer.
    """
    required_css_class = 'required'


class AddOnRadioSelect(forms.RadioSelect):
    option_template_name = 'pretixpresale/forms/addon_choice_option.html'

    def optgroups(self, name, value, attrs=None):
        attrs = attrs or {}
        groups = []
        has_selected = False
        for index, (option_value, option_label, option_desc) in enumerate(chain(self.choices)):
            if option_value is None:
                option_value = ''
            if isinstance(option_label, (list, tuple)):
                raise TypeError('Choice groups are not supported here')
            group_name = None
            subgroup = []
            groups.append((group_name, subgroup, index))

            selected = (
                force_text(option_value) in value and
                (has_selected is False or self.allow_multiple_selected)
            )
            if selected is True and has_selected is False:
                has_selected = True
            attrs['description'] = option_desc
            subgroup.append(self.create_option(
                name, option_value, option_label, selected, index,
                subindex=None, attrs=attrs,
            ))

        return groups


class AddOnVariationField(forms.ChoiceField):
    def valid_value(self, value):
        text_value = force_text(value)
        for k, v, d in self.choices:
            if value == k or text_value == force_text(k):
                return True
        return False


class AddOnsForm(forms.Form):
    """
    This form class is responsible for selecting add-ons to a product in the cart.
    """

    def _label(self, event, item_or_variation, avail, override_price=None):
        if isinstance(item_or_variation, ItemVariation):
            variation = item_or_variation
            item = item_or_variation.item
            price = variation.price
            label = variation.value
        else:
            item = item_or_variation
            price = item.default_price
            label = item.name

        if override_price:
            price = override_price

        if self.price_included:
            price = TAXED_ZERO
        else:
            price = item.tax(price)

        if not price.gross:
            n = '{name}'.format(
                name=label
            )
        elif not price.rate:
            n = _('{name} (+ {price})').format(
                name=label, price=money_filter(price.gross, event.currency)
            )
        elif event.settings.display_net_prices:
            n = _('{name} (+ {price} plus {taxes}% {taxname})').format(
                name=label, price=money_filter(price.net, event.currency),
                taxes=number_format(price.rate), taxname=price.name
            )
        else:
            n = _('{name} (+ {price} incl. {taxes}% {taxname})').format(
                name=label, price=money_filter(price.gross, event.currency),
                taxes=number_format(price.rate), taxname=price.name
            )

        if avail[0] < 20:
            n += ' – {}'.format(_('SOLD OUT'))
        elif avail[0] < 100:
            n += ' – {}'.format(_('Currently unavailable'))
        else:
            if avail[1] is not None and event.settings.show_quota_left:
                n += ' – {}'.format(_('%(num)s currently available') % {'num': avail[1]})

        return n

    def __init__(self, *args, **kwargs):
        """
        Takes additional keyword arguments:

        :param category: The category to choose from
        :param event: The event this belongs to
        :param subevent: The event the parent cart position belongs to
        :param initial: The current set of add-ons
        :param quota_cache: A shared dictionary for quota caching
        :param item_cache: A shared dictionary for item/category caching
        """
        category = kwargs.pop('category')
        event = kwargs.pop('event')
        subevent = kwargs.pop('subevent')
        current_addons = kwargs.pop('initial')
        quota_cache = kwargs.pop('quota_cache')
        item_cache = kwargs.pop('item_cache')
        self.price_included = kwargs.pop('price_included')
        self.sales_channel = kwargs.pop('sales_channel')

        super().__init__(*args, **kwargs)

        if subevent:
            item_price_override = subevent.item_price_overrides
            var_price_override = subevent.var_price_overrides
        else:
            item_price_override = {}
            var_price_override = {}

        ckey = '{}-{}'.format(subevent.pk if subevent else 0, category.pk)
        if ckey not in item_cache:
            # Get all items to possibly show
            items = category.items.filter(
                Q(active=True)
                & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
                & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
                & Q(hide_without_voucher=False)
                & Q(sales_channels__contains=self.sales_channel)
            ).select_related('tax_rule').prefetch_related(
                Prefetch('quotas',
                         to_attr='_subevent_quotas',
                         queryset=event.quotas.filter(subevent=subevent)),
                Prefetch('variations', to_attr='available_variations',
                         queryset=ItemVariation.objects.filter(active=True, quotas__isnull=False).prefetch_related(
                             Prefetch('quotas',
                                      to_attr='_subevent_quotas',
                                      queryset=event.quotas.filter(subevent=subevent))
                         ).distinct()),
            ).annotate(
                quotac=Count('quotas'),
                has_variations=Count('variations')
            ).filter(
                quotac__gt=0
            ).order_by('category__position', 'category_id', 'position', 'name')
            item_cache[ckey] = items
        else:
            items = item_cache[ckey]

        for i in items:
            if i.has_variations:
                choices = [('', _('no selection'), '')]
                for v in i.available_variations:
                    cached_availability = v.check_quotas(subevent=subevent, _cache=quota_cache)
                    if v._subevent_quotas:
                        choices.append(
                            (v.pk,
                             self._label(event, v, cached_availability,
                                         override_price=var_price_override.get(v.pk)),
                             v.description)
                        )

                field = AddOnVariationField(
                    choices=choices,
                    label=i.name,
                    required=False,
                    widget=AddOnRadioSelect,
                    help_text=rich_text(str(i.description)),
                    initial=current_addons.get(i.pk),
                )
                if len(choices) > 1:
                    self.fields['item_%s' % i.pk] = field
            else:
                if not i._subevent_quotas:
                    continue
                cached_availability = i.check_quotas(subevent=subevent, _cache=quota_cache)
                field = forms.BooleanField(
                    label=self._label(event, i, cached_availability,
                                      override_price=item_price_override.get(i.pk)),
                    required=False,
                    initial=i.pk in current_addons,
                    help_text=rich_text(str(i.description)),
                )
                self.fields['item_%s' % i.pk] = field
