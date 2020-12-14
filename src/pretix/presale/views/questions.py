from django.utils.functional import cached_property

from pretix.base.views.mixins import BaseQuestionsViewMixin
from pretix.presale.forms.checkout import QuestionsForm
from pretix.presale.views import get_cart


class QuestionsViewMixin(BaseQuestionsViewMixin):
    form_class = QuestionsForm
    only_user_visible = True

    @cached_property
    def _positions_for_questions(self):
        cart = get_cart(self.request)
        return sorted(list(cart), key=self._keyfunc)
