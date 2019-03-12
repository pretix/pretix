from django.db.models import Prefetch
from django.utils.functional import cached_property

from pretix.base.models import Question, QuestionAnswer, QuestionOption
from pretix.base.views.mixins import BaseQuestionsViewMixin
from pretix.presale.forms.checkout import QuestionsForm
from pretix.presale.views import get_cart


class QuestionsViewMixin(BaseQuestionsViewMixin):
    form_class = QuestionsForm
    only_user_visible = True

    @cached_property
    def _positions_for_questions(self):
        qqs = self.request.event.questions.all()
        if self.only_user_visible:
            qqs = qqs.filter(ask_during_checkin=False)
        cart = get_cart(self.request).select_related(
            'addon_to'
        ).prefetch_related(
            'addons', 'addons__item', 'addons__variation',
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
        )
        return sorted(list(cart), key=self._keyfunc)
