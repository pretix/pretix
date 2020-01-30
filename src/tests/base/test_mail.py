import os

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import scope

from pretix.base.models import Event, Organizer, User
from pretix.base.services.mail import mail


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    user.email = 'dummy@dummy.dummy'
    user.save()
    with scope(organizer=o):
        yield event, user, o


@pytest.mark.django_db
def test_send_mail_with_prefix(env):
    djmail.outbox = []
    event, user, organizer = env
    event.settings.set('mail_prefix', 'test')
    mail('dummy@dummy.dummy', 'Test subject', 'mailtest.txt', {}, event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert djmail.outbox[0].subject == '[test] Test subject'


@pytest.mark.django_db
def test_send_mail_with_event_sender(env):
    djmail.outbox = []
    event, user, organizer = env
    event.settings.set('mail_from', 'foo@bar')
    mail('dummy@dummy.dummy', 'Test subject', 'mailtest.txt', {}, event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert djmail.outbox[0].subject == 'Test subject'
    assert djmail.outbox[0].from_email == 'Dummy <foo@bar>'


@pytest.mark.django_db
def test_send_mail_with_event_signature(env):
    djmail.outbox = []
    event, user, organizer = env
    event.settings.set('mail_text_signature', 'This is a test signature.')
    mail('dummy@dummy.dummy', 'Test subject', 'mailtest.txt', {}, event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert 'This is a test signature.' in djmail.outbox[0].body


@pytest.mark.django_db
def test_send_mail_with_default_sender(env):
    djmail.outbox = []
    event, user, organizer = env
    mail('dummy@dummy.dummy', 'Test subject', 'mailtest.txt', {}, event)
    del event.settings['mail_from']

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert djmail.outbox[0].subject == 'Test subject'
    assert djmail.outbox[0].from_email == 'Dummy <%s>' % settings.MAIL_FROM


@pytest.mark.django_db
@pytest.mark.skipif(
    not os.path.exists(os.path.join(settings.LOCALE_PATHS[0], 'de', 'LC_MESSAGES', 'django.mo')),
    reason="requires locale files to be compiled"
)
def test_send_mail_with_user_locale(env):
    djmail.outbox = []
    event, user, organizer = env
    user.locale = 'de'
    user.save()
    mail('dummy@dummy.dummy', _('User'), 'mailtest.txt', {}, event, locale=user.locale)
    del event.settings['mail_from']

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == 'Benutzer'
    assert 'The language code used for rendering this e-mail is de.' in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_placeholder(env):
    djmail.outbox = []
    event, user, organizer = env
    mail('dummy@dummy.dummy', '{event} Test subject', 'mailtest.txt', {"event": event}, event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert djmail.outbox[0].subject == 'Dummy Test subject'
