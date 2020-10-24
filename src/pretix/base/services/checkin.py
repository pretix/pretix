from datetime import timedelta

import dateutil
from django.db import transaction
from django.db.models.functions import TruncDate
from django.dispatch import receiver
from django.utils.functional import cached_property
from django.utils.timezone import now, override
from django.utils.translation import gettext as _
from django_scopes import scope, scopes_disabled

from pretix.base.models import (
    Checkin, CheckinList, Device, Order, OrderPosition, QuestionOption,
)
from pretix.base.signals import checkin_created, order_placed, periodic_task
from pretix.helpers.jsonlogic import Logic


def get_logic_environment(ev):
    def build_time(t=None, value=None):
        if t == "custom":
            return dateutil.parser.parse(value)
        elif t == 'date_from':
            return ev.date_from
        elif t == 'date_to':
            return ev.date_to
        elif t == 'date_admission':
            return ev.date_admission or ev.date_from

    def is_before(t1, t2, tolerance=None):
        if tolerance:
            return t1 < t2 + timedelta(minutes=float(tolerance))
        else:
            return t1 < t2

    logic = Logic()
    logic.add_operation('objectList', lambda *objs: list(objs))
    logic.add_operation('lookup', lambda model, pk, str: int(pk))
    logic.add_operation('inList', lambda a, b: a in b)
    logic.add_operation('buildTime', build_time)
    logic.add_operation('isBefore', is_before)
    logic.add_operation('isAfter', lambda t1, t2, tol=None: is_before(t2, t1, tol))
    return logic


class LazyRuleVars:
    def __init__(self, position, clist, dt):
        self._position = position
        self._clist = clist
        self._dt = dt

    def __getitem__(self, item):
        if item[0] != '_' and hasattr(self, item):
            return getattr(self, item)
        raise KeyError()

    @property
    def now(self):
        return self._dt

    @property
    def product(self):
        return self._position.item_id

    @property
    def variation(self):
        return self._position.variation_id

    @cached_property
    def entries_number(self):
        return self._position.checkins.filter(type=Checkin.TYPE_ENTRY, list=self._clist).count()

    @cached_property
    def entries_today(self):
        tz = self._clist.event.timezone
        midnight = now().astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        return self._position.checkins.filter(type=Checkin.TYPE_ENTRY, list=self._clist, datetime__gte=midnight).count()

    @cached_property
    def entries_days(self):
        tz = self._clist.event.timezone
        with override(tz):
            return self._position.checkins.filter(list=self._clist, type=Checkin.TYPE_ENTRY).annotate(
                day=TruncDate('datetime')
            ).values('day').distinct().count()


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
                    user=None, auth=None, canceled_supported=False, type=Checkin.TYPE_ENTRY):
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

    # Lock order positions
    op = OrderPosition.all.select_for_update().get(pk=op.pk)
    checkin_questions = list(
        clist.event.questions.filter(ask_during_checkin=True, items__in=[op.item_id])
    )

    if op.canceled or op.order.status not in (Order.STATUS_PAID, Order.STATUS_PENDING):
        raise CheckInError(
            _('This order position has been canceled.'),
            'canceled' if canceled_supported else 'unpaid'
        )

    require_answers = []
    if checkin_questions:
        answers = {a.question: a for a in op.answers.all()}
        for q in checkin_questions:
            if q not in given_answers and q not in answers:
                require_answers.append(q)

        _save_answers(op, answers, given_answers)

    if not clist.all_products and op.item_id not in [i.pk for i in clist.limit_products.all()]:
        raise CheckInError(
            _('This order position has an invalid product for this check-in list.'),
            'product'
        )
    elif clist.subevent_id and op.subevent_id != clist.subevent_id:
        raise CheckInError(
            _('This order position has an invalid date for this check-in list.'),
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

    if type == Checkin.TYPE_ENTRY and clist.rules and not force:
        rule_data = LazyRuleVars(op, clist, dt)
        logic = get_logic_environment(op.subevent or clist.event)
        if not logic.apply(clist.rules, rule_data):
            raise CheckInError(
                _('This entry is not permitted due to custom rules.'),
                'rules'
            )

    device = None
    if isinstance(auth, Device):
        device = auth

    last_ci = op.checkins.order_by('-datetime').filter(list=clist).only('type', 'nonce').first()
    entry_allowed = (
        type == Checkin.TYPE_EXIT or
        clist.allow_multiple_entries or
        last_ci is None or
        (clist.allow_entry_after_exit and last_ci.type == Checkin.TYPE_EXIT)
    )

    if nonce and ((last_ci and last_ci.nonce == nonce) or op.checkins.filter(type=type, list=clist, device=device, nonce=nonce).exists()):
        return

    if entry_allowed or force:
        ci = Checkin.objects.create(
            position=op,
            type=type,
            list=clist,
            datetime=dt,
            device=device,
            gate=device.gate if device else None,
            nonce=nonce,
            forced=force and not entry_allowed,
        )
        op.order.log_action('pretix.event.checkin', data={
            'position': op.id,
            'positionid': op.positionid,
            'first': True,
            'forced': force or op.order.status != Order.STATUS_PAID,
            'datetime': dt,
            'type': type,
            'list': clist.pk
        }, user=user, auth=auth)
        checkin_created.send(op.order.event, checkin=ci)
    else:
        raise CheckInError(
            _('This ticket has already been redeemed.'),
            'already_redeemed',
        )


@receiver(order_placed, dispatch_uid="autocheckin_order_placed")
def order_placed(sender, **kwargs):
    order = kwargs['order']
    event = sender

    cls = list(event.checkin_lists.filter(auto_checkin_sales_channels__contains=order.sales_channel).prefetch_related(
        'limit_products'))
    if not cls:
        return
    for op in order.positions.all():
        for cl in cls:
            if cl.all_products or op.item_id in {i.pk for i in cl.limit_products.all()}:
                if not cl.subevent_id or cl.subevent_id == op.subevent_id:
                    ci = Checkin.objects.create(position=op, list=cl, auto_checked_in=True, type=Checkin.TYPE_ENTRY)
                    checkin_created.send(event, checkin=ci)


@receiver(periodic_task, dispatch_uid="autocheckin_exit_all")
@scopes_disabled()
def process_exit_all(sender, **kwargs):
    qs = CheckinList.objects.filter(
        exit_all_at__lte=now(),
        exit_all_at__isnull=False
    ).select_related('event', 'event__organizer')
    for cl in qs:
        for p in cl.positions_inside:
            with scope(organizer=cl.event.organizer):
                ci = Checkin.objects.create(
                    position=p, list=cl, auto_checked_in=True, type=Checkin.TYPE_EXIT, datetime=cl.exit_all_at
                )
                checkin_created.send(cl.event, checkin=ci)
        cl.exit_all_at = cl.exit_all_at + timedelta(days=1)
        cl.save(update_fields=['exit_all_at'])
