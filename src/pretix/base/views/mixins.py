import json
from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Prefetch, QuerySet
from django.utils.functional import cached_property

from pretix.base.forms.questions import (
    BaseInvoiceAddressForm, BaseInvoiceNameForm, BaseQuestionsForm,
)
from pretix.base.models import (
    CartPosition, InvoiceAddress, OrderPosition, Question, QuestionAnswer,
    QuestionOption,
)


class BaseQuestionsViewMixin:
    form_class = BaseQuestionsForm
    all_optional = False

    @staticmethod
    def _keyfunc(pos):
        # Sort addons after the item they are an addon to
        if isinstance(pos, OrderPosition):
            i = pos.addon_to.positionid if pos.addon_to else pos.positionid
        else:
            i = pos.addon_to.pk if pos.addon_to else pos.pk
        addon_penalty = 1 if pos.addon_to else 0
        return i, addon_penalty, pos.pk

    @cached_property
    def _positions_for_questions(self):
        raise NotImplementedError()

    @cached_property
    def forms(self):
        """
        A list of forms with one form for each cart position that has questions
        the user can answer. All forms have a custom prefix, so that they can all be
        submitted at once.
        """
        formlist = []
        for cr in self._positions_for_questions:
            cartpos = cr if isinstance(cr, CartPosition) else None
            orderpos = cr if isinstance(cr, OrderPosition) else None
            form = self.form_class(event=self.request.event,
                                   prefix=cr.id,
                                   cartpos=cartpos,
                                   orderpos=orderpos,
                                   all_optional=self.all_optional,
                                   data=(self.request.POST if self.request.method == 'POST' else None),
                                   files=(self.request.FILES if self.request.method == 'POST' else None))
            form.pos = cartpos or orderpos
            form.show_copy_answers_to_addon_button = form.pos.addon_to and set(form.pos.addon_to.item.questions.all()) & set(form.pos.item.questions.all())
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
                # This form was correctly filled, so we store the data as
                # answers to the questions / in the CartPosition object
                for k, v in form.cleaned_data.items():
                    if k == 'attendee_name_parts':
                        form.pos.attendee_name_parts = v if v else None
                    elif k == 'attendee_email':
                        form.pos.attendee_email = v if v != '' else None
                    elif k == 'company':
                        form.pos.company = v if v != '' else None
                    elif k == 'street':
                        form.pos.street = v if v != '' else None
                    elif k == 'zipcode':
                        form.pos.zipcode = v if v != '' else None
                    elif k == 'city':
                        form.pos.city = v if v != '' else None
                    elif k == 'country':
                        form.pos.country = v if v != '' else None
                    elif k == 'state':
                        form.pos.state = v if v != '' else None
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
                        elif v != '' and v is not None:
                            answer = QuestionAnswer(
                                cartposition=(form.pos if isinstance(form.pos, CartPosition) else None),
                                orderposition=(form.pos if isinstance(form.pos, OrderPosition) else None),
                                question=field.question,
                            )
                            self._save_to_answer(field, answer, v)
                            answer.save()
                    else:
                        meta_info.setdefault('question_form_data', {})
                        if v is None:
                            if k in meta_info['question_form_data']:
                                del meta_info['question_form_data'][k]
                        else:
                            meta_info['question_form_data'][k] = v

            form.pos.meta_info = json.dumps(meta_info)
            form.pos.save()
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
    def invoice_form(self):
        if not self.address_asked and self.request.event.settings.invoice_name_required:
            return self.invoice_name_form_class(
                data=self.request.POST if self.request.method == "POST" else None,
                event=self.request.event,
                instance=self.invoice_address, validate_vat_id=False,
                all_optional=self.all_optional
            )
        if self.address_asked:
            return self.invoice_form_class(
                data=self.request.POST if self.request.method == "POST" else None,
                event=self.request.event,
                instance=self.invoice_address, validate_vat_id=False,
                all_optional=self.all_optional,
            )
        else:
            return forms.Form(data=self.request.POST if self.request.method == "POST" else None)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['formgroups'] = self.formdict.items()
        ctx['invoice_form'] = self.invoice_form
        ctx['invoice_address_asked'] = self.address_asked
        return ctx
