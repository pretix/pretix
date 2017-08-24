import logging
import os
from decimal import Decimal
from itertools import chain

import vat_moss.errors
import vat_moss.id
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.utils.encoding import force_text
from django.utils.formats import number_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import ItemVariation, Question
from pretix.base.models.orders import InvoiceAddress, OrderPosition
from pretix.base.models.tax import EU_COUNTRIES, TAXED_ZERO
from pretix.base.templatetags.rich_text import rich_text
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.signals import contact_form_fields, question_form_fields

logger = logging.getLogger(__name__)


class ContactForm(forms.Form):
    required_css_class = 'required'
    email = forms.EmailField(label=_('E-mail'),
                             help_text=_('Make sure to enter a valid email address. We will send you an order '
                                         'confirmation including a link that you need in case you want to make '
                                         'modifications to your order or download your ticket later.'),
                             widget=forms.EmailInput(attrs={'data-typocheck-target': '1'}))

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        if self.event.settings.order_email_asked_twice:
            self.fields['email_repeat'] = forms.EmailField(
                label=_('E-mail address (repeated)'),
                help_text=_('Please enter the same email address again to make sure you typed it correctly.')
            )

        responses = contact_form_fields.send(self.event)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value

    def clean(self):
        if self.event.settings.order_email_asked_twice:
            if self.cleaned_data.get('email').lower() != self.cleaned_data.get('email_repeat').lower():
                raise ValidationError(_('Please enter the same email address twice.'))


class BusinessBooleanRadio(forms.RadioSelect):
    def __init__(self, attrs=None):
        choices = (
            ('individual', _('Individual customer')),
            ('business', _('Business customer')),
        )
        super().__init__(attrs, choices)

    def format_value(self, value):
        try:
            return {True: 'business', False: 'individual'}[value]
        except KeyError:
            return 'individual'

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        return {
            'business': True,
            True: True,
            'True': True,
            'individual': False,
            'False': False,
            False: False,
        }.get(value)


class InvoiceAddressForm(forms.ModelForm):
    required_css_class = 'required'

    class Meta:
        model = InvoiceAddress
        fields = ('is_business', 'company', 'name', 'street', 'zipcode', 'city', 'country', 'vat_id')
        widgets = {
            'is_business': BusinessBooleanRadio,
            'street': forms.Textarea(attrs={'rows': 2, 'placeholder': _('Street and Number')}),
            'company': forms.TextInput(attrs={'data-typocheck-source': '1',
                                              'data-display-dependency': '#id_is_business_1'}),
            'name': forms.TextInput(attrs={'data-typocheck-source': '1'}),
            'vat_id': forms.TextInput(attrs={'data-display-dependency': '#id_is_business_1'}),
        }
        labels = {
            'is_business': ''
        }

    def __init__(self, *args, **kwargs):
        self.event = event = kwargs.pop('event')
        self.request = kwargs.pop('request', None)
        self.validate_vat_id = kwargs.pop('validate_vat_id')
        super().__init__(*args, **kwargs)
        if not event.settings.invoice_address_vatid:
            del self.fields['vat_id']
        if not event.settings.invoice_address_required:
            for k, f in self.fields.items():
                f.required = False
                f.widget.is_required = False
                if 'required' in f.widget.attrs:
                    del f.widget.attrs['required']

            if event.settings.invoice_name_required:
                self.fields['name'].required = True
        else:
            self.fields['company'].widget.attrs['data-required-if'] = '#id_is_business_1'
            self.fields['name'].widget.attrs['data-required-if'] = '#id_is_business_0'

    def clean(self):
        data = self.cleaned_data
        if not data.get('name') and not data.get('company') and self.event.settings.invoice_address_required:
            raise ValidationError(_('You need to provide either a company name or your name.'))

        if 'vat_id' in self.changed_data or not data.get('vat_id'):
            self.instance.vat_id_validated = False

        if self.validate_vat_id and self.instance.vat_id_validated and 'vat_id' not in self.changed_data:
            pass
        elif self.validate_vat_id and data.get('is_business') and data.get('country') in EU_COUNTRIES and data.get('vat_id'):
            if data.get('vat_id')[:2] != str(data.get('country')):
                raise ValidationError(_('Your VAT ID does not match the selected country.'))
            try:
                result = vat_moss.id.validate(data.get('vat_id'))
                if result:
                    country_code, normalized_id, company_name = result
                    self.instance.vat_id_validated = True
                    self.instance.vat_id = normalized_id
            except vat_moss.errors.InvalidError:
                raise ValidationError(_('This VAT ID is not valid. Please re-check your input.'))
            except vat_moss.errors.WebServiceUnavailableError:
                logger.exception('VAT ID checking failed for country {}'.format(data.get('country')))
                self.instance.vat_id_validated = False
                if self.request:
                    messages.warning(self.request, _('Your VAT ID could not be checked, as the VAT checking service of '
                                                     'your country is currently not available. We will therefore '
                                                     'need to charge VAT on your invoice. You can get the tax amount '
                                                     'back via the VAT reimbursement process.'))
        else:
            self.instance.vat_id_validated = False


class UploadedFileWidget(forms.ClearableFileInput):
    def __init__(self, *args, **kwargs):
        self.position = kwargs.pop('position')
        self.event = kwargs.pop('event')
        self.answer = kwargs.pop('answer')
        super().__init__(*args, **kwargs)

    class FakeFile:
        def __init__(self, file, position, event, answer):
            self.file = file
            self.position = position
            self.event = event
            self.answer = answer

        def __str__(self):
            return os.path.basename(self.file.name).split('.', 1)[-1]

        @property
        def url(self):
            if isinstance(self.position, OrderPosition):
                return eventreverse(self.event, 'presale:event.order.download.answer', kwargs={
                    'order': self.position.order.code,
                    'secret': self.position.order.secret,
                    'answer': self.answer.pk,
                })
            else:
                return eventreverse(self.event, 'presale:event.cart.download.answer', kwargs={
                    'answer': self.answer.pk,
                })

    def format_value(self, value):
        if self.is_initial(value):
            return self.FakeFile(value, self.position, self.event, self.answer)


class QuestionsForm(forms.Form):
    """
    This form class is responsible for asking order-related questions. This includes
    the attendee name for admission tickets, if the corresponding setting is enabled,
    as well as additional questions defined by the organizer.
    """
    required_css_class = 'required'

    def __init__(self, *args, **kwargs):
        """
        Takes two additional keyword arguments:

        :param cartpos: The cart position the form should be for
        :param event: The event this belongs to
        """
        cartpos = self.cartpos = kwargs.pop('cartpos', None)
        orderpos = self.orderpos = kwargs.pop('orderpos', None)
        pos = cartpos or orderpos
        item = pos.item
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
                    help_text=q.help_text,
                    initial=initialbool, widget=widget,
                )
            elif q.type == Question.TYPE_NUMBER:
                field = forms.DecimalField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=initial.answer if initial else None,
                    min_value=Decimal('0.00')
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    widget=forms.Textarea,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE:
                field = forms.ModelChoiceField(
                    queryset=q.options.all(),
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    widget=forms.RadioSelect,
                    initial=initial.options.first() if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE_MULTIPLE:
                field = forms.ModelMultipleChoiceField(
                    queryset=q.options.all(),
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    widget=forms.CheckboxSelectMultiple,
                    initial=initial.options.all() if initial else None,
                )
            elif q.type == Question.TYPE_FILE:
                field = forms.FileField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=initial.file if initial else None,
                    widget=UploadedFileWidget(position=pos, event=event, answer=initial)
                )
            field.question = q
            if answers:
                # Cache the answer object for later use
                field.answer = answers[0]
            self.fields['question_%s' % q.id] = field

        responses = question_form_fields.send(sender=event, position=pos)
        data = pos.meta_info_data
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
                value.initial = data.get('question_form_data', {}).get(key)


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
            n = _('{name} (+ {currency} {price})').format(
                name=label, currency=event.currency, price=number_format(price.gross)
            )
        elif event.settings.display_net_prices:
            n = _('{name} (+ {currency} {price} plus {taxes}% {taxname})').format(
                name=label, currency=event.currency, price=number_format(price.net),
                taxes=number_format(price.rate), taxname=price.name
            )
        else:
            n = _('{name} (+ {currency} {price} incl. {taxes}% {taxname})').format(
                name=label, currency=event.currency, price=number_format(price.gross),
                taxes=number_format(price.rate), taxname=price.name
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
