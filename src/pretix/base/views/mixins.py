#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import datetime
import json
from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError
from django.db.models import Prefetch, QuerySet
from django.utils.functional import cached_property
from django.utils.timezone import make_aware

from pretix.base.forms.questions import (
    BaseInvoiceAddressForm, BaseInvoiceNameForm, BaseQuestionsForm,
)
from pretix.base.models import (
    CartPosition, InvoiceAddress, OrderPosition, Question, QuestionAnswer,
    QuestionOption,
)
from pretix.base.models.customers import AttendeeProfile
from pretix.presale.signals import contact_form_fields_overrides


class BaseQuestionsViewMixin:
    form_class = BaseQuestionsForm
    all_optional = False

    @cached_property
    def _positions_for_questions(self):
        raise NotImplementedError()

    def get_question_override_sets(self, position, index):
        return []

    def question_form_kwargs(self, cr):
        return {}

    @cached_property
    def forms(self):
        """
        A list of forms with one form for each cart position that has questions
        the user can answer. All forms have a custom prefix, so that they can all be
        submitted at once.
        """
        formlist = []
        for idx, cr in enumerate(self._positions_for_questions):
            cartpos = cr if isinstance(cr, CartPosition) else None
            orderpos = cr if isinstance(cr, OrderPosition) else None

            kwargs = self.question_form_kwargs(cr)
            form = self.form_class(event=self.request.event,
                                   prefix=cr.id,
                                   request=self.request,
                                   cartpos=cartpos,
                                   orderpos=orderpos,
                                   all_optional=self.all_optional,
                                   data=(self.request.POST if self.request.method == 'POST' else None),
                                   files=(self.request.FILES if self.request.method == 'POST' else None),
                                   **kwargs)
            form.pos = cartpos or orderpos
            form.show_copy_answers_to_addon_button = form.pos.addon_to and (
                set(form.pos.addon_to.item.questions.all()) & set(form.pos.item.questions.all()) or
                (form.pos.addon_to.item.ask_attendee_data and form.pos.item.ask_attendee_data and (
                    self.request.event.settings.attendee_names_asked or
                    self.request.event.settings.attendee_emails_asked or
                    self.request.event.settings.attendee_company_asked or
                    self.request.event.settings.attendee_addresses_asked
                ))
            )

            override_sets = self.get_question_override_sets(cr, idx)
            for overrides in override_sets:
                for question_name, question_field in form.fields.items():
                    if hasattr(question_field, 'question'):
                        src = overrides.get(question_field.question.identifier)
                    else:
                        src = overrides.get(question_name)
                    if not src:
                        continue

                    if 'disabled' in src:
                        question_field.disabled = src['disabled']
                    if 'initial' in src:
                        if question_field.disabled:
                            question_field.initial = src['initial']
                        else:
                            question_field.initial = getattr(question_field, 'initial', None) or src['initial']
                    if 'validators' in src:
                        question_field.validators += src['validators']

            if len(form.fields) > 0:
                formlist.append(form)
        return formlist

    @cached_property
    def formdict(self):
        storage = OrderedDict()
        for f in self.forms:
            pos = f.pos
            if pos.addon_to_id:
                if pos.addon_to not in storage:
                    storage[pos.addon_to] = []
                storage[pos.addon_to].append(f)
            else:
                if pos not in storage:
                    storage[pos] = []
                storage[pos].append(f)
        return storage

    def save(self):
        failed = False
        for form in self.forms:
            meta_info = form.pos.meta_info_data
            # Every form represents a CartPosition or OrderPosition with questions attached
            if not form.is_valid():
                failed = True
            else:
                if form.cleaned_data.get('saved_id'):
                    prof = AttendeeProfile.objects.filter(
                        customer=self.cart_customer, pk=form.cleaned_data.get('saved_id')
                    ).first() or AttendeeProfile(customer=getattr(self, 'cart_customer', None))
                    answers_key_to_index = {a.get('field_name'): i for i, a in enumerate(prof.answers)}
                else:
                    prof = AttendeeProfile(customer=getattr(self, 'cart_customer', None))
                    answers_key_to_index = {}

                # This form was correctly filled, so we store the data as
                # answers to the questions / in the CartPosition object
                for k, v in form.cleaned_data.items():
                    if k in ('save', 'saved_id'):
                        continue
                    elif k == 'attendee_name_parts':
                        form.pos.attendee_name_parts = v if v else None
                        prof.attendee_name_parts = form.pos.attendee_name_parts
                        prof.attendee_name_cached = form.pos.attendee_name
                    elif k in ('attendee_email', 'company', 'street', 'zipcode', 'city', 'country', 'state'):
                        v = v if v != '' else None
                        setattr(form.pos, k, v)
                        setattr(prof, k, v)
                    elif k == 'requested_valid_from':
                        if isinstance(v, datetime.datetime):
                            form.pos.requested_valid_from = v
                        elif isinstance(v, datetime.date):
                            form.pos.requested_valid_from = make_aware(datetime.datetime.combine(
                                v,
                                datetime.time(hour=0, minute=0, second=0, microsecond=0)
                            ), self.request.event.timezone)
                        else:
                            form.pos.requested_valid_from = None
                    elif k.startswith('question_'):
                        field = form.fields[k]
                        if hasattr(field, 'answer'):
                            # We already have a cached answer object, so we don't
                            # have to create a new one
                            if v == '' or v is None or (isinstance(field, forms.FileField) and v is False) \
                                    or (isinstance(v, QuerySet) and not v.exists()):
                                if field.answer.file:
                                    field.answer.file.delete()
                                field.answer.delete()
                            else:
                                self._save_to_answer(field, field.answer, v)
                                field.answer.save()
                                if isinstance(field, forms.ModelMultipleChoiceField) or isinstance(field, forms.ModelChoiceField):
                                    answer_value = {o.identifier: str(o) for o in field.answer.options.all()}
                                elif isinstance(field, forms.BooleanField):
                                    answer_value = bool(field.answer.answer)
                                else:
                                    answer_value = str(field.answer.answer)
                                answer_dict = {
                                    'field_name': k,
                                    'field_label': str(field.label),
                                    'value': answer_value,
                                    'question_type': field.question.type,
                                    'question_identifier': field.question.identifier,
                                }
                                if k in answers_key_to_index:
                                    prof.answers[answers_key_to_index[k]] = answer_dict
                                else:
                                    prof.answers.append(answer_dict)
                        elif v != '' and v is not None:
                            answer = QuestionAnswer(
                                cartposition=(form.pos if isinstance(form.pos, CartPosition) else None),
                                orderposition=(form.pos if isinstance(form.pos, OrderPosition) else None),
                                question=field.question,
                            )
                            try:
                                self._save_to_answer(field, answer, v)
                                answer.save()
                            except IntegrityError:
                                # Since we prefill ``field.answer`` at form creation time, there's a possible race condition
                                # here if the users submits their save request a second time while the first one is still running,
                                # thus leading to duplicate QuestionAnswer objects. Since Django doesn't support UPSERT, the "proper"
                                # fix would be a transaction with select_for_update(), or at least fetching using get_or_create here
                                # again. However, both of these approaches have a significant performance overhead for *all* requests,
                                # while the issue happens very very rarely. So we opt for just catching the error and retrying properly.
                                answer = QuestionAnswer.objects.get(
                                    cartposition=(form.pos if isinstance(form.pos, CartPosition) else None),
                                    orderposition=(form.pos if isinstance(form.pos, OrderPosition) else None),
                                    question=field.question,
                                )
                                self._save_to_answer(field, answer, v)
                                answer.save()

                            if isinstance(field, forms.ModelMultipleChoiceField) or isinstance(field, forms.ModelChoiceField):
                                answer_value = {o.identifier: str(o) for o in answer.options.all()}
                            elif isinstance(field, forms.BooleanField):
                                answer_value = bool(answer.answer)
                            else:
                                answer_value = str(answer.answer)
                            answer_dict = {
                                'field_name': k,
                                'field_label': str(field.label),
                                'value': answer_value,
                                'question_type': field.question.type,
                                'question_identifier': field.question.identifier,
                            }
                            if k in answers_key_to_index:
                                prof.answers[answers_key_to_index[k]] = answer_dict
                            else:
                                prof.answers.append(answer_dict)

                    else:
                        field = form.fields[k]

                        meta_info.setdefault('question_form_data', {})
                        if v is None:
                            if k in meta_info['question_form_data']:
                                del meta_info['question_form_data'][k]
                        else:
                            meta_info['question_form_data'][k] = v

                        answer_dict = {
                            'field_name': k,
                            'field_label': str(field.label),
                            'value': str(v),
                            'question_type': None,
                            'question_identifier': None,
                        }
                        if k in answers_key_to_index:
                            prof.answers[answers_key_to_index[k]] = answer_dict
                        else:
                            prof.answers.append(answer_dict)

            form.pos.meta_info = json.dumps(meta_info)
            form.pos.save()

            if form.cleaned_data.get('save') and not failed:
                prof.save()
                self.cart_session[f'saved_attendee_profile_{form.pos.pk}'] = prof.pk

        return not failed

    def _save_to_answer(self, field, answer, value):
        if isinstance(field, forms.ModelMultipleChoiceField):
            answstr = ", ".join([str(o) for o in value])
            if not answer.pk:
                answer.save()
            else:
                answer.options.clear()
            answer.answer = answstr
            answer.options.add(*value)
        elif isinstance(field, forms.ModelChoiceField):
            if not answer.pk:
                answer.save()
            else:
                answer.options.clear()
            answer.options.add(value)
            answer.answer = value.answer
        elif isinstance(field, forms.FileField):
            if isinstance(value, UploadedFile):
                answer.file.save(value.name, value)
                answer.answer = 'file://' + value.name
        else:
            answer.answer = value


class OrderQuestionsViewMixin(BaseQuestionsViewMixin):
    invoice_form_class = BaseInvoiceAddressForm
    invoice_name_form_class = BaseInvoiceNameForm
    only_user_visible = True
    all_optional = False

    @cached_property
    def _positions_for_questions(self):
        return self.positions

    @cached_property
    def positions(self):
        qqs = self.request.event.questions.all()
        if self.only_user_visible:
            qqs = qqs.filter(ask_during_checkin=False, hidden=False)
        return list(self.order.positions.select_related(
            'item', 'variation'
        ).prefetch_related(
            Prefetch('answers',
                     QuestionAnswer.objects.prefetch_related('options'),
                     to_attr='answerlist'),
            Prefetch('item__questions',
                     qqs.prefetch_related(
                         Prefetch('options', QuestionOption.objects.prefetch_related(Prefetch(
                             # This prefetch statement is utter bullshit, but it actually prevents Django from doing
                             # a lot of queries since ModelChoiceIterator stops trying to be clever once we have
                             # a prefetch lookup on this query...
                             'question',
                             Question.objects.none(),
                             to_attr='dummy'
                         )))
                     ).select_related('dependency_question'),
                     to_attr='questions_to_ask')
        ))

    @cached_property
    def invoice_address(self):
        try:
            return self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            return InvoiceAddress(order=self.order)

    @cached_property
    def address_asked(self):
        return self.request.event.settings.invoice_address_asked and (
            self.order.total != Decimal('0.00') or not self.request.event.settings.invoice_address_not_asked_free
        )

    @cached_property
    def _contact_override_sets(self):
        override_sets = [
            resp for recv, resp in contact_form_fields_overrides.send(
                self.request.event,
                request=self.request,
                order=self.order,
            )
        ]
        for override in override_sets:
            for k in override:
                # We don't want initial values to be modified, they should come from the order directly
                override[k].pop('initial', None)
        return override_sets

    @cached_property
    def vat_id_validation_enabled(self):
        return any([p.item.tax_rule and (p.item.tax_rule.eu_reverse_charge or p.item.tax_rule.custom_rules)
                    for p in self.positions])

    @cached_property
    def invoice_form(self):
        if not self.address_asked and self.request.event.settings.invoice_name_required:
            f = self.invoice_name_form_class(
                data=self.request.POST if self.request.method == "POST" else None,
                event=self.request.event,
                instance=self.invoice_address,
                validate_vat_id=False,
                request=self.request,
                all_optional=self.all_optional
            )
        elif self.address_asked:
            f = self.invoice_form_class(
                data=self.request.POST if self.request.method == "POST" else None,
                event=self.request.event,
                instance=self.invoice_address,
                validate_vat_id=self.vat_id_validation_enabled,
                request=self.request,
                all_optional=self.all_optional,
            )
        else:
            f = forms.Form(data=self.request.POST if self.request.method == "POST" else None)

        override_sets = self._contact_override_sets
        for overrides in override_sets:
            for fname, val in overrides.items():
                if 'disabled' in val and fname in f.fields:
                    f.fields[fname].disabled = val['disabled']

        return f

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['formgroups'] = self.formdict.items()
        ctx['invoice_form'] = self.invoice_form
        ctx['invoice_address_asked'] = self.address_asked
        return ctx
