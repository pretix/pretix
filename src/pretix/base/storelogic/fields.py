from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.utils.translation import gettext_lazy as _

from pretix.base.models import CartPosition, Question
from pretix.base.services.checkin import _save_answers
from pretix.base.storelogic import IncompleteError
from pretix.presale.signals import question_form_fields


class Field:
    @property
    def identifier(self):
        raise NotImplementedError()

    @property
    def label(self):
        raise NotImplementedError()

    @property
    def help_text(self):
        raise NotImplementedError()

    @property
    def type(self):
        raise NotImplementedError()

    @property
    def required(self):
        return True

    @property
    def validation_hints(self):
        raise {}

    def validate_input(self, value):
        return value


class PositionField(Field):
    def save_input(self, position, value):
        raise NotImplementedError()

    def current_value(self, position):
        raise NotImplementedError()


class SessionField(Field):
    def save_input(self, session_data, value):
        raise NotImplementedError()

    def current_value(self, session_data):
        raise NotImplementedError()


class QuestionField(PositionField):
    def __init__(self, question: Question):
        self.question = question

    @property
    def label(self):
        return self.question.question

    @property
    def help_text(self):
        return self.question.help_text

    @property
    def type(self):
        return self.question.type

    @property
    def identifier(self):
        return f"question_{self.question.identifier}"

    def validate_input(self, value):
        return self.question.clean_answer(value)

    def required(self, value):
        return self.question.required

    def validation_hints(self):
        d = {
            "valid_number_min": self.question.valid_number_min,
            "valid_number_max": self.question.valid_number_max,
            "valid_date_min": self.question.valid_date_min,
            "valid_date_max": self.question.valid_date_max,
            "valid_datetime_min": self.question.valid_datetime_min,
            "valid_datetime_max": self.question.valid_datetime_max,
            "valid_string_length_max": self.question.valid_string_length_max,
            "dependency_on": f"question_{self.question.dependency_question.identifier}" if self.question.dependency_question_id else None,
            "dependency_values": self.question.dependency_values,
        }
        if self.question.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
            d["choices"] = [
                {
                    "identifier": opt.identifier,
                    "label": str(opt.answer)
                }
                for opt in self.question.options.all()
            ]
        return d

    def save_input(self, position, value):
        answers = [a for a in position.answerlist if a.question_id == self.question.id]
        if answers:
            answers = {self.question: answers[0]}
        else:
            answers = {}
        _save_answers(position, answers, {self.question: value})

    def current_value(self, position):
        answers = [a for a in position.answerlist if a.question_id == self.question.id]
        if answers:
            if self.question.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
                return ",".join([a.idenitifer for a in answers[0].options.all()])
            else:
                return answers[0].answer


class SyntheticSessionField(SessionField):
    def __init__(self, label, help_text, type, identifier, required, save_func, get_func, validate_func):
        self._label = label
        self._help_text = help_text
        self._type = type
        self._identifier = identifier
        self._required = required
        self._save_func = save_func
        self._get_func = get_func
        self._validate_func = validate_func
        super().__init__()

    @property
    def label(self):
        return self._label

    @property
    def help_text(self):
        return self._help_text

    @property
    def type(self):
        return self._type

    @property
    def required(self):
        return self._required

    @property
    def identifier(self):
        return self._identifier

    def validation_hints(self):
        return {}

    def save_input(self, session_data, value):
        self._save_func(session_data, value)

    def current_value(self, session_data):
        return self._get_func(session_data)

    def validate_input(self, value):
        return self._validate_func(value)


def get_checkout_fields(event):
    fields = []
    # TODO: support contact_form_fields
    # TODO: support contact_form_fields_override

    # email
    fields.append(SyntheticSessionField(
        label=_("Email"),
        help_text=None,
        type=Question.TYPE_STRING,  # TODO: Add a type?
        identifier="email",
        required=True,
        get_func=lambda session_data: session_data.get("email"),
        save_func=lambda session_data, value: session_data.update({"email": value}),
        validate_func=lambda value: EmailValidator()(value) or value,
    ))

    # TODO: phone
    # TODO: invoice address
    return fields


def get_position_fields(event, pos: CartPosition):
    # TODO: support override sets
    fields = []

    for q in pos.item.questions_to_ask:
        fields.append(QuestionField(q))

    return fields


def ensure_fields_are_completed(event, positions, cart_session, invoice_address, all_optional, cart_is_free):
    try:
        emailval = EmailValidator()
        if not cart_session.get('email') and not all_optional:
            raise IncompleteError(_('Please enter a valid email address.'))
        if cart_session.get('email'):
            emailval(cart_session.get('email'))
    except ValidationError:
        raise IncompleteError(_('Please enter a valid email address.'))

    address_asked = (
        event.settings.invoice_address_asked and (not event.settings.invoice_address_not_asked_free or not cart_is_free)
    )

    if not all_optional:
        if address_asked:
            if event.settings.invoice_address_required and (not invoice_address or not invoice_address.street):
                raise IncompleteError(_('Please enter your invoicing address.'))

        if event.settings.invoice_name_required and (not invoice_address or not invoice_address.name):
            raise IncompleteError(_('Please enter your name.'))

    for cp in positions:
        answ = {
            aw.question_id: aw for aw in cp.answerlist
        }
        question_cache = {
            q.pk: q for q in cp.item.questions_to_ask
        }

        def question_is_visible(parentid, qvals):
            if parentid not in question_cache:
                return False
            parentq = question_cache[parentid]
            if parentq.dependency_question_id and not question_is_visible(parentq.dependency_question_id,
                                                                          parentq.dependency_values):
                return False
            if parentid not in answ:
                return False
            return (
                ('True' in qvals and answ[parentid].answer == 'True')
                or ('False' in qvals and answ[parentid].answer == 'False')
                or (any(qval in [o.identifier for o in answ[parentid].options.all()] for qval in qvals))
            )

        def question_is_required(q):
            return (
                q.required and
                (not q.dependency_question_id or question_is_visible(q.dependency_question_id, q.dependency_values))
            )

        if not all_optional:
            for q in cp.item.questions_to_ask:
                if question_is_required(q) and q.id not in answ:
                    raise IncompleteError(_('Please fill in answers to all required questions.'))
            if cp.item.ask_attendee_data and event.settings.get('attendee_names_required', as_type=bool) \
                    and not cp.attendee_name_parts:
                raise IncompleteError(_('Please fill in answers to all required questions.'))
            if cp.item.ask_attendee_data and event.settings.get('attendee_emails_required', as_type=bool) \
                    and cp.attendee_email is None:
                raise IncompleteError(_('Please fill in answers to all required questions.'))
            if cp.item.ask_attendee_data and event.settings.get('attendee_company_required', as_type=bool) \
                    and cp.company is None:
                raise IncompleteError(_('Please fill in answers to all required questions.'))
            if cp.item.ask_attendee_data and event.settings.get('attendee_addresses_required', as_type=bool) \
                    and (cp.street is None and cp.city is None and cp.country is None):
                raise IncompleteError(_('Please fill in answers to all required questions.'))

        responses = question_form_fields.send(sender=event, position=cp)
        form_data = cp.meta_info_data.get('question_form_data', {})
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                if value.required and not form_data.get(key):
                    raise IncompleteError(_('Please fill in answers to all required questions.'))
