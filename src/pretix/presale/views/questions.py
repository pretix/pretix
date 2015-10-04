from django.utils.functional import cached_property

from pretix.base.models import CartPosition, OrderPosition, QuestionAnswer
from pretix.presale.forms.checkout import QuestionsForm


class QuestionsViewMixin:
    @cached_property
    def forms(self):
        """
        A list of forms with one form for each cart cart position that has questions
        the user can answer. All forms have a custom prefix, so that they can all be
        submitted at once.
        """
        formlist = []
        for cr in self.positions:
            cartpos = cr if isinstance(cr, CartPosition) else None
            orderpos = cr if isinstance(cr, OrderPosition) else None
            form = QuestionsForm(event=self.request.event,
                                 prefix=cr.identity,
                                 cartpos=cartpos,
                                 orderpos=orderpos,
                                 data=(self.request.POST if self.request.method == 'POST' else None))
            form.pos = cartpos or orderpos
            if len(form.fields) > 0:
                formlist.append(form)
        return formlist

    def save(self):
        failed = False
        for form in self.forms:
            # Every form represents a CartPosition or OrderPosition with questions attached
            if not form.is_valid():
                failed = True
            else:
                # This form was correctly filled, so we store the data as
                # answers to the questions / in the CartPosition object
                for k, v in form.cleaned_data.items():
                    if k == 'attendee_name':
                        form.pos = form.pos.clone()
                        form.pos.attendee_name = v if v != '' else None
                        form.pos.save()
                    elif k.startswith('question_') and v is not None:
                        field = form.fields[k]
                        if hasattr(field, 'answer'):
                            # We already have a cached answer object, so we don't
                            # have to create a new one
                            if v == '':
                                field.answer.delete()
                            else:
                                field.answer = field.answer.clone()
                                field.answer.answer = v
                                field.answer.save()
                        elif v != '':
                            QuestionAnswer.objects.create(
                                cartposition=(form.pos if isinstance(form.pos, CartPosition) else None),
                                orderposition=(form.pos if isinstance(form.pos, OrderPosition) else None),
                                question=field.question,
                                answer=v
                            )
        return not failed
