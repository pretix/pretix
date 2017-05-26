from decimal import Decimal
from itertools import chain

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.utils.encoding import force_text
from django.utils.formats import number_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import ItemVariation, Question
from pretix.base.models.orders import InvoiceAddress
from pretix.base.templatetags.rich_text import rich_text
from pretix.presale.signals import contact_form_fields


class ContactForm(forms.Form):
    email = forms.EmailField(label=_('E-mail'),
                             help_text=_('Make sure to enter a valid email address. We will send you an order '
                                         'confirmation including a link that you need in case you want to make '
                                         'modifications to your order or download your ticket later.'),
                             widget=forms.EmailInput(attrs={'data-typocheck-target': '1'}))

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        responses = contact_form_fields.send(self.event)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value


class InvoiceAddressForm(forms.ModelForm):

    class Meta:
        model = InvoiceAddress
        fields = ('company', 'name', 'street', 'zipcode', 'city', 'country', 'vat_id')
        widgets = {
            'street': forms.Textarea(attrs={'rows': 2, 'placeholder': _('Street and Number')}),
            'company': forms.TextInput(attrs={'data-typocheck-source': '1'}),
            'name': forms.TextInput(attrs={'data-typocheck-source': '1'}),
        }

    def __init__(self, *args, **kwargs):
        self.event = event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        if not event.settings.invoice_address_vatid:
            del self.fields['vat_id']
        if not event.settings.invoice_address_required:
            for k, f in self.fields.items():
                f.required = False
                f.widget.is_required = False
                if 'required' in f.widget.attrs:
                    del f.widget.attrs['required']

    def clean(self):
        data = self.cleaned_data
        if not data['name'] and not data['company'] and self.event.settings.invoice_address_required:
            raise ValidationError(_('You need to provide either a company name or your name.'))


class QuestionsForm(forms.Form):
    """
    This form class is responsible for asking order-related questions. This includes
    the attendee name for admission tickets, if the corresponding setting is enabled,
    as well as additional questions defined by the organizer.
    """

    def __init__(self, *args, **kwargs):
        """
        Takes two additional keyword arguments:

        :param cartpos: The cart position the form should be for
        :param event: The event this belongs to
        """
        cartpos = self.cartpos = kwargs.pop('cartpos', None)
        orderpos = self.orderpos = kwargs.pop('orderpos', None)
        item = cartpos.item if cartpos else orderpos.item
        questions = list(item.questions.all())
        event = kwargs.pop('event')

        super().__init__(*args, **kwargs)

        if item.admission and event.settings.attendee_names_asked:
            self.fields['attendee_name'] = forms.CharField(
                max_length=255, required=event.settings.attendee_names_required,
                label=_('Attendee name'),
                initial=(cartpos.attendee_name if cartpos else orderpos.attendee_name),
                widget=forms.TextInput(attrs={'data-typocheck-source': '1'}),
            )
        if item.admission and event.settings.attendee_emails_asked:
            self.fields['attendee_email'] = forms.EmailField(
                required=event.settings.attendee_emails_required,
                label=_('Attendee email'),
                initial=(cartpos.attendee_email if cartpos else orderpos.attendee_email)
            )

        for q in questions:
            # Do we already have an answer? Provide it as the initial value
            answers = [
                a for a
                in (cartpos.answers.all() if cartpos else orderpos.answers.all())
                if a.question_id == q.id
            ]
            if answers:
                initial = answers[0]
            else:
                initial = None
            if q.type == Question.TYPE_BOOLEAN:
                if q.required:
                    # For some reason, django-bootstrap3 does not set the required attribute
                    # itself.
                    widget = forms.CheckboxInput(attrs={'required': 'required'})
                else:
                    widget = forms.CheckboxInput()

                if initial:
                    initialbool = (initial.answer == "True")
                else:
                    initialbool = False

                field = forms.BooleanField(
                    label=q.question, required=q.required,
                    initial=initialbool, widget=widget
                )
            elif q.type == Question.TYPE_NUMBER:
                field = forms.DecimalField(
                    label=q.question, required=q.required,
                    initial=initial.answer if initial else None,
                    min_value=Decimal('0.00')
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    widget=forms.Textarea,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE:
                field = forms.ModelChoiceField(
                    queryset=q.options.all(),
                    label=q.question, required=q.required,
                    widget=forms.RadioSelect,
                    initial=initial.options.first() if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE_MULTIPLE:
                field = forms.ModelMultipleChoiceField(
                    queryset=q.options.all(),
                    label=q.question, required=q.required,
                    widget=forms.CheckboxSelectMultiple,
                    initial=initial.options.all() if initial else None,
                )
            field.question = q
            if answers:
                # Cache the answer object for later use
                field.answer = answers[0]
            self.fields['question_%s' % q.id] = field


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

    def _label(self, event, item_or_variation, avail):
        if isinstance(item_or_variation, ItemVariation):
            variation = item_or_variation
            item = item_or_variation.item
            price = variation.price
            price_net = variation.net_price
            label = variation.value
        else:
            item = item_or_variation
            price = item.default_price
            price_net = item.default_price_net
            label = item.name

        if not price:
            n = '{name}'.format(
                name=label
            )
        elif not item.tax_rate:
            n = _('{name} (+ {currency} {price})').format(
                name=label, currency=event.currency, price=number_format(price)
            )
        elif event.settings.display_net_prices:
            n = _('{name} (+ {currency} {price} plus {taxes}% taxes)').format(
                name=label, currency=event.currency, price=number_format(price_net),
                taxes=number_format(item.tax_rate)
            )
        else:
            n = _('{name} (+ {currency} {price} incl. {taxes}% taxes)').format(
                name=label, currency=event.currency, price=number_format(price),
                taxes=number_format(item.tax_rate)
            )

        if avail[0] < 20:
            n += ' – {}'.format(_('SOLD OUT'))
        elif avail[0] < 100:
            n += ' – {}'.format(_('Currently unavailable'))

        return n

    def __init__(self, *args, **kwargs):
        """
        Takes additional keyword arguments:

        :param category: The category to choose from
        :param event: The event this belongs to
        :param initial: The current set of add-ons
        :param quota_cache: A shared dictionary for quota caching
        :param item_cache: A shared dictionary for item/category caching
        """
        category = kwargs.pop('category')
        event = kwargs.pop('event')
        current_addons = kwargs.pop('initial')
        quota_cache = kwargs.pop('quota_cache')
        item_cache = kwargs.pop('item_cache')

        super().__init__(*args, **kwargs)

        if category.pk not in item_cache:
            # Get all items to possibly show
            items = category.items.filter(
                Q(active=True)
                & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
                & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
                & Q(hide_without_voucher=False)
            ).prefetch_related(
                'variations__quotas',  # for .availability()
                Prefetch('quotas', queryset=event.quotas.all()),
                Prefetch('variations', to_attr='available_variations',
                         queryset=ItemVariation.objects.filter(active=True, quotas__isnull=False).distinct()),
            ).annotate(
                quotac=Count('quotas'),
                has_variations=Count('variations')
            ).filter(
                quotac__gt=0
            ).order_by('category__position', 'category_id', 'position', 'name')
            item_cache[category.pk] = items
        else:
            items = item_cache[category.pk]

        for i in items:
            if i.has_variations:
                choices = [('', _('no selection'), '')]
                for v in i.available_variations:
                    cached_availability = v.check_quotas(_cache=quota_cache)
                    choices.append((v.pk, self._label(event, v, cached_availability), v.description))

                field = AddOnVariationField(
                    choices=choices,
                    label=i.name,
                    required=False,
                    widget=AddOnRadioSelect,
                    help_text=rich_text(str(i.description)),
                    initial=current_addons.get(i.pk),
                )
            else:
                cached_availability = i.check_quotas(_cache=quota_cache)
                field = forms.BooleanField(
                    label=self._label(event, i, cached_availability),
                    required=False,
                    initial=i.pk in current_addons,
                    help_text=rich_text(str(i.description)),
                )

            self.fields['item_%s' % i.pk] = field
