from django.db import transaction
from django.db.models import Prefetch
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.models import (
    Checkin, CheckinList, Order, OrderPosition, Question, QuestionOption,
)
from pretix.base.signals import order_placed


class CheckInError(Exception):
    def __init__(self, msg, code):
        self.msg = msg
        self.code = code
        super().__init__(msg)


class RequiredQuestionsError(Exception):
    def __init__(self, msg, code, questions):
        self.msg = msg
        self.code = code
        self.questions = questions
        super().__init__(msg)


def _save_answers(op, answers, given_answers):
    for q, a in given_answers.items():
        if not a:
            if q in answers:
                answers[q].delete()
            else:
                continue
        if isinstance(a, QuestionOption):
            if q in answers:
                qa = answers[q]
                qa.answer = str(a.answer)
                qa.save()
                qa.options.clear()
            else:
                qa = op.answers.create(question=q, answer=str(a.answer))
            qa.options.add(a)
        elif isinstance(a, list):
            if q in answers:
                qa = answers[q]
                qa.answer = ", ".join([str(o) for o in a])
                qa.save()
                qa.options.clear()
            else:
                qa = op.answers.create(question=q, answer=", ".join([str(o) for o in a]))
            qa.options.add(*a)
        else:
            if q in answers:
                qa = answers[q]
                qa.answer = str(a)
                qa.save()
            else:
                op.answers.create(question=q, answer=str(a))


@transaction.atomic
def perform_checkin(op: OrderPosition, clist: CheckinList, given_answers: dict, force=False,
                    ignore_unpaid=False, nonce=None, datetime=None, questions_supported=True,
                    user=None, auth=None, canceled_supported=False):
    """
    Create a checkin for this particular order position and check-in list. Fails with CheckInError if the check in is
    not valid at this time.

    :param op: The order position to check in
    :param clist: The order position to check in
    :param given_answers: A dictionary of questions mapped to validated, given answers
    :param force: When set to True, this will succeed even when the position is already checked in or when required
        questions are not filled out.
    :param ignore_unpaid: When set to True, this will succeed even when the order is unpaid.
    :param questions_supported: When set to False, questions are ignored
    :param nonce: A random nonce to prevent race conditions.
    :param datetime: The datetime of the checkin, defaults to now.
    """
    dt = datetime or now()

    # Fetch order position with related objects
    op = OrderPosition.all.select_related(
        'item', 'variation', 'order', 'addon_to'
    ).prefetch_related(
        'item__questions',
        Prefetch(
            'item__questions',
            queryset=Question.objects.filter(ask_during_checkin=True),
            to_attr='checkin_questions'
        ),
        'answers'
    ).get(pk=op.pk)

    if op.canceled or op.order.status not in (Order.STATUS_PAID, Order.STATUS_PENDING):
        raise CheckInError(
            _('This order position has been canceled.'),
            'canceled' if canceled_supported else 'unpaid'
        )

    answers = {a.question: a for a in op.answers.all()}
    require_answers = []
    for q in op.item.checkin_questions:
        if q not in given_answers and q not in answers:
            require_answers.append(q)

    _save_answers(op, answers, given_answers)

    if not clist.all_products and op.item_id not in [i.pk for i in clist.limit_products.all()]:
        raise CheckInError(
            _('This order position has an invalid product for this check-in list.'),
            'product'
        )
    elif op.order.status != Order.STATUS_PAID and not force and not (
        ignore_unpaid and clist.include_pending and op.order.status == Order.STATUS_PENDING
    ):
        raise CheckInError(
            _('This order is not marked as paid.'),
            'unpaid'
        )
    elif require_answers and not force and questions_supported:
        raise RequiredQuestionsError(
            _('You need to answer questions to complete this check-in.'),
            'incomplete',
            require_answers
        )
    else:
        try:
            ci, created = Checkin.objects.get_or_create(position=op, list=clist, defaults={
                'datetime': dt,
                'nonce': nonce,
            })
        except Checkin.MultipleObjectsReturned:
            ci, created = Checkin.objects.filter(position=op, list=clist).last(), False

    if created or (nonce and nonce == ci.nonce):
        if created:
            op.order.log_action('pretix.event.checkin', data={
                'position': op.id,
                'positionid': op.positionid,
                'first': True,
                'forced': op.order.status != Order.STATUS_PAID,
                'datetime': dt,
                'list': clist.pk
            }, user=user, auth=auth)
    else:
        if not force:
            raise CheckInError(
                _('This ticket has already been redeemed.'),
                'already_redeemed',
            )
        op.order.log_action('pretix.event.checkin', data={
            'position': op.id,
            'positionid': op.positionid,
            'first': False,
            'forced': force,
            'datetime': dt,
            'list': clist.pk
        }, user=user, auth=auth)


@receiver(order_placed, dispatch_uid="autocheckin_order_placed")
def order_placed(sender, **kwargs):
    order = kwargs['order']
    event = sender

    cls = list(event.checkin_lists.filter(auto_checkin_sales_channels__contains=order.sales_channel).prefetch_related(
        'limit_products'))
    for op in order.positions.all():
        for cl in cls:
            if cl.all_products or op.item_id in {i.pk for i in cl.limit_products.all()}:
                Checkin.objects.create(position=op, list=cl, auto_checked_in=True)
