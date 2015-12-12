from django import forms
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Question


class ContactForm(forms.Form):
    email = forms.EmailField(label=_('E-mail'))


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
        cartpos = kwargs.pop('cartpos', None)
        orderpos = kwargs.pop('orderpos', None)
        item = cartpos.item if cartpos else orderpos.item
        questions = list(item.questions.all())
        event = kwargs.pop('event')

        super().__init__(*args, **kwargs)

        if item.admission and event.settings.attendee_names_asked:
            self.fields['attendee_name'] = forms.CharField(
                max_length=255, required=event.settings.attendee_names_required,
                label=_('Attendee name'),
                initial=(cartpos.attendee_name if cartpos else orderpos.attendee_name)
            )

        for q in questions:
            # Do we already have an answer? Provide it as the initial value
            answers = [
                a for a
                in (cartpos.answers.all() if cartpos else orderpos.answers.all())
                if a.question_id == q.id
            ]
            if answers:
                initial = answers[0].answer
            else:
                initial = None
            if q.type == Question.TYPE_BOOLEAN:
                field = forms.BooleanField(
                    label=q.question, required=q.required,
                    initial=initial
                )
            elif q.type == Question.TYPE_NUMBER:
                field = forms.DecimalField(
                    label=q.question, required=q.required,
                    initial=initial
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    initial=initial
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    widget=forms.Textarea,
                    initial=initial
                )
            field.question = q
            if answers:
                # Cache the answer object for later use
                field.answer = answers[0]
            self.fields['question_%s' % q.id] = field
