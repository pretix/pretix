from itertools import chain

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch
from django.utils.encoding import force_text
from django.utils.formats import number_format
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms.questions import (
    BaseInvoiceAddressForm, BaseQuestionsForm,
)
from pretix.base.models import ItemVariation, Quota
from pretix.base.models.tax import TAXED_ZERO
from pretix.base.services.cart import CartError, error_messages
from pretix.base.signals import validate_cart_addons
from pretix.base.templatetags.money import money_filter
from pretix.base.templatetags.rich_text import rich_text
from pretix.base.validators import EmailBlacklistValidator
from pretix.helpers.templatetags.thumb import thumb
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
        self.all_optional = kwargs.pop('all_optional', False)
        super().__init__(*args, **kwargs)

        if self.event.settings.order_email_asked_twice:
            self.fields['email_repeat'] = forms.EmailField(
                label=_('E-mail address (repeated)'),
                help_text=_('Please enter the same email address again to make sure you typed it correctly.'),
            )

        if not self.request.session.get('iframe_session', False):
            # There is a browser quirk in Chrome that leads to incorrect initial scrolling in iframes if there
            # is an autofocus field. Who would have thought… See e.g. here:
            # https://floatboxjs.com/forum/topic.php?post=8440&usebb_sid=2e116486a9ec6b7070e045aea8cded5b#post8440
            self.fields['email'].widget.attrs['autofocus'] = 'autofocus'

        responses = contact_form_fields.send(self.event, request=self.request)
        for r, response in responses:
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
        if self.all_optional:
            for k, v in self.fields.items():
                v.required = False
                v.widget.is_required = False

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

        if avail[0] < Quota.AVAILABILITY_RESERVED:
            n += ' – {}'.format(_('SOLD OUT'))
        elif avail[0] < Quota.AVAILABILITY_OK:
            n += ' – {}'.format(_('Currently unavailable'))
        else:
            if avail[1] is not None and item.do_show_quota_left:
                n += ' – {}'.format(_('%(num)s currently available') % {'num': avail[1]})

        if not isinstance(item_or_variation, ItemVariation) and item.picture:
            n = escape(n)
            n += '<br>'
            n += '<a href="{}" class="productpicture" data-title="{}" data-lightbox={}>'.format(
                item.picture.url, escape(escape(item.name)), item.id
            )
            n += '<img src="{}" alt="{}">'.format(
                thumb(item.picture, '60x60^'),
                escape(item.name)
            )
            n += '</a>'
            n = mark_safe(n)
        return n

    def __init__(self, *args, **kwargs):
        """
        Takes additional keyword arguments:

        :param iao: The ItemAddOn object
        :param event: The event this belongs to
        :param subevent: The event the parent cart position belongs to
        :param initial: The current set of add-ons
        :param quota_cache: A shared dictionary for quota caching
        :param item_cache: A shared dictionary for item/category caching
        """
        self.iao = kwargs.pop('iao')
        category = self.iao.addon_category
        self.event = kwargs.pop('event')
        subevent = kwargs.pop('subevent')
        current_addons = kwargs.pop('initial')
        quota_cache = kwargs.pop('quota_cache')
        item_cache = kwargs.pop('item_cache')
        self.price_included = kwargs.pop('price_included')
        self.sales_channel = kwargs.pop('sales_channel')
        self.base_position = kwargs.pop('base_position')

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
            items = category.items.filter_available(
                channel=self.sales_channel,
                allow_addons=True
            ).select_related('tax_rule').prefetch_related(
                Prefetch('quotas',
                         to_attr='_subevent_quotas',
                         queryset=self.event.quotas.filter(subevent=subevent)),
                Prefetch('variations', to_attr='available_variations',
                         queryset=ItemVariation.objects.filter(active=True, quotas__isnull=False).prefetch_related(
                             Prefetch('quotas',
                                      to_attr='_subevent_quotas',
                                      queryset=self.event.quotas.filter(subevent=subevent))
                         ).distinct()),
                'event'
            ).annotate(
                quotac=Count('quotas'),
                has_variations=Count('variations')
            ).filter(
                quotac__gt=0
            ).order_by('category__position', 'category_id', 'position', 'name')
            item_cache[ckey] = items
        else:
            items = item_cache[ckey]

        self.vars_cache = {}

        for i in items:
            if i.hidden_if_available:
                q = i.hidden_if_available.availability(_cache=quota_cache)
                if q[0] == Quota.AVAILABILITY_OK:
                    continue

            if i.has_variations:
                choices = [('', _('no selection'), '')]
                for v in i.available_variations:
                    cached_availability = v.check_quotas(subevent=subevent, _cache=quota_cache)
                    if self.event.settings.hide_sold_out and cached_availability[0] < Quota.AVAILABILITY_RESERVED:
                        continue

                    if v._subevent_quotas:
                        self.vars_cache[v.pk] = v
                        choices.append(
                            (v.pk,
                             self._label(self.event, v, cached_availability,
                                         override_price=var_price_override.get(v.pk)),
                             v.description)
                        )

                n = i.name
                if i.picture:
                    n = escape(n)
                    n += '<br>'
                    n += '<a href="{}" class="productpicture" data-title="{}" data-lightbox="{}">'.format(
                        i.picture.url, escape(escape(i.name)), i.id
                    )
                    n += '<img src="{}" alt="{}">'.format(
                        thumb(i.picture, '60x60^'),
                        escape(i.name)
                    )
                    n += '</a>'
                    n = mark_safe(n)
                field = AddOnVariationField(
                    choices=choices,
                    label=n,
                    required=False,
                    widget=AddOnRadioSelect,
                    help_text=rich_text(str(i.description)),
                    initial=current_addons.get(i.pk),
                )
                field.item = i
                if len(choices) > 1:
                    self.fields['item_%s' % i.pk] = field
            else:
                if not i._subevent_quotas:
                    continue
                cached_availability = i.check_quotas(subevent=subevent, _cache=quota_cache)
                if self.event.settings.hide_sold_out and cached_availability[0] < Quota.AVAILABILITY_RESERVED:
                    continue
                field = forms.BooleanField(
                    label=self._label(self.event, i, cached_availability,
                                      override_price=item_price_override.get(i.pk)),
                    required=False,
                    initial=i.pk in current_addons,
                    help_text=rich_text(str(i.description)),
                )
                field.item = i
                self.fields['item_%s' % i.pk] = field

    def clean(self):
        data = super().clean()
        selected = set()
        for k, v in data.items():
            if v is True:
                selected.add((self.fields[k].item, None))
            elif v:
                selected.add((self.fields[k].item, self.vars_cache.get(int(v))))
        if len(selected) > self.iao.max_count:
            # TODO: Proper pluralization
            raise ValidationError(
                _(error_messages['addon_max_count']),
                'addon_max_count',
                {
                    'base': str(self.iao.base_item.name),
                    'max': self.iao.max_count,
                    'cat': str(self.iao.addon_category.name),
                }
            )
        elif len(selected) < self.iao.min_count:
            # TODO: Proper pluralization
            raise ValidationError(
                _(error_messages['addon_min_count']),
                'addon_min_count',
                {
                    'base': str(self.iao.base_item.name),
                    'min': self.iao.min_count,
                    'cat': str(self.iao.addon_category.name),
                }
            )
        try:
            validate_cart_addons.send(sender=self.event, addons=selected, base_position=self.base_position,
                                      iao=self.iao)
        except CartError as e:
            raise ValidationError(str(e))
