#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Sanket Dasgupta
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime
import os
import re
from decimal import Decimal
from email.mime.text import MIMEText

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.test import override_settings
from django.utils.html import escape
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import scope, scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.models import (
    Event, InvoiceAddress, Order, Organizer, OutgoingMail, User,
)
from pretix.base.services.mail import mail, mail_send_task


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    prop1 = o.meta_properties.get_or_create(name="Test")[0]
    prop2 = o.meta_properties.get_or_create(name="Website")[0]
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    event.meta_values.update_or_create(property=prop1, defaults={'value': "*Beep*"})
    event.meta_values.update_or_create(property=prop2, defaults={'value': "https://example.com"})
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    user.email = 'dummy@dummy.dummy'
    user.save()
    with scope(organizer=o):
        yield event, user, o


@pytest.fixture
@scopes_disabled()
def item(env):
    return env[0].items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
@scopes_disabled()
def order(env, item):
    event, _, _ = env
    o = Order.objects.create(
        code="FOO",
        event=event,
        email="dummy@dummy.test",
        status=Order.STATUS_PENDING,
        secret="k24fiuwvu8kxz3y1",
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
        datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc),
        total=23,
        locale="en",
    )
    o.positions.create(
        order=o,
        item=item,
        variation=None,
        price=Decimal("23"),
        attendee_email="peter@example.org",
        attendee_name_parts={"given_name": "Peter", "family_name": "Miller"},
        secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
        pseudonymization_id="ABCDEFGHKL",
    )
    InvoiceAddress.objects.create(
        order=o,
        name_parts={"given_name": "Peter", "family_name": "Miller"},
    )
    return o


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


@pytest.mark.django_db
@pytest.mark.parametrize("smtp_use_custom", (True, False))
def test_send_mail_custom_event_smtp(env, smtp_use_custom):
    djmail.outbox = []
    event, user, organizer = env
    event.settings.set("smtp_use_custom", smtp_use_custom)

    mail('dummy@dummy.dummy', 'Test subject', 'mailtest.txt', {}, event=event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert djmail.outbox[0].subject == 'Test subject'


@pytest.mark.django_db
@pytest.mark.parametrize("smtp_use_custom", (True, False))
def test_send_mail_custom_organizer_smtp(env, smtp_use_custom):
    djmail.outbox = []
    event, user, organizer = env
    organizer.settings.set("smtp_use_custom", smtp_use_custom)

    mail('dummy@dummy.dummy', 'Test subject', 'mailtest.txt', {}, organizer=organizer)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert djmail.outbox[0].subject == 'Test subject'


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
    assert 'The language code used for rendering this email is de.' in djmail.outbox[0].body


@pytest.mark.django_db
def test_queue_state_sent(env):
    m = OutgoingMail.objects.create(
        to=['recipient@example.com'],
        subject='Test',
        body_plain='Test',
        sender='sender@example.com',
    )
    assert m.status == OutgoingMail.STATUS_QUEUED
    mail_send_task.apply(kwargs={
        'outgoing_mail': m.pk,
    }, max_retries=0)
    m.refresh_from_db()
    assert m.status == OutgoingMail.STATUS_SENT


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND='pretix.testutils.mail.PermanentlyFailingEmailBackend')
def test_queue_state_permanent_failure(env):
    m = OutgoingMail.objects.create(
        to=['recipient@example.com'],
        subject='Test',
        body_plain='Test',
        sender='sender@example.com',
    )
    assert m.status == OutgoingMail.STATUS_QUEUED
    mail_send_task.apply(kwargs={
        'outgoing_mail': m.pk,
    }, max_retries=0)
    m.refresh_from_db()
    assert m.status == OutgoingMail.STATUS_FAILED


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND='pretix.testutils.mail.FailingEmailBackend')
def test_queue_state_retry_failure(env, monkeypatch):
    def retry(*args, **kwargs):
        raise Exception()

    monkeypatch.setattr('celery.app.task.Task.retry', retry, raising=True)
    m = OutgoingMail.objects.create(
        to=['recipient@example.com'],
        subject='Test',
        body_plain='Test',
        sender='sender@example.com',
    )
    assert m.status == OutgoingMail.STATUS_QUEUED
    mail_send_task.apply(kwargs={
        'outgoing_mail': m.pk,
    }, max_retries=0)
    m.refresh_from_db()
    assert m.status == OutgoingMail.STATUS_AWAITING_RETRY
    assert m.retry_after > now()


@pytest.mark.django_db
def test_queue_state_foreign_key_handling():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )

    mail_queued = OutgoingMail.objects.create(
        organizer=o,
        event=event,
        to=['recipient@example.com'],
        subject='Test',
        body_plain='Test',
        sender='sender@example.com',
    )
    mail_sent = OutgoingMail.objects.create(
        organizer=o,
        event=event,
        to=['recipient@example.com'],
        subject='Test',
        body_plain='Test',
        sender='sender@example.com',
        status=OutgoingMail.STATUS_SENT,
    )

    event.delete()

    assert not OutgoingMail.objects.filter(pk=mail_queued.pk).exists()
    assert OutgoingMail.objects.get(pk=mail_sent.pk).event is None

    o.delete()
    assert not OutgoingMail.objects.filter(pk=mail_sent.pk).exists()


@pytest.mark.django_db
def test_sendmail_placeholder(env):
    djmail.outbox = []
    event, user, organizer = env
    mail('dummy@dummy.dummy', '{event} Test subject', 'mailtest.txt', {"event": event.name}, event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert djmail.outbox[0].subject == 'Dummy Test subject'


def _extract_html(mail):
    for content, mimetype in mail.alternatives:
        if "multipart/related" in mimetype:
            for sp in content._payload:
                if isinstance(sp, MIMEText):
                    return sp._payload
                    break
        elif "text/html" in mimetype:
            return content


@pytest.mark.django_db
def test_placeholder_html_rendering_from_template(env):
    djmail.outbox = []
    event, user, organizer = env
    event.name = "<strong>event & co. kg</strong> {currency}"
    event.save()
    mail('dummy@dummy.dummy', '{event} Test subject', 'mailtest.txt', get_email_context(
        event=event,
        payment_info="**IBAN**: 123  \n**BIC**: 456",
    ), event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    # Known bug for now: These should not have HTML for the plain body, but we'll fix this safter the security release
    assert escape('Event name: <strong>event & co. kg</strong> {currency}') in djmail.outbox[0].body
    assert '<strong>IBAN</strong>: 123<br>\n<strong>BIC</strong>: 456' in djmail.outbox[0].body
    assert '**Meta**: <em>Beep</em>' in djmail.outbox[0].body
    assert escape('Event website: [<strong>event & co. kg</strong> {currency}](https://example.org/dummy)') in djmail.outbox[0].body
    # todo: assert '&lt;' not in djmail.outbox[0].body
    # todo: assert '&amp;' not in djmail.outbox[0].body
    assert 'Unevaluated placeholder: {currency}' in djmail.outbox[0].body
    assert 'EUR' not in djmail.outbox[0].body
    html = _extract_html(djmail.outbox[0])

    assert '<strong>event' not in html
    assert 'Event name: &lt;strong&gt;event &amp; co. kg&lt;/strong&gt; {currency}' in html
    assert '<strong>IBAN</strong>: 123<br/>\n<strong>BIC</strong>: 456' in html
    assert '<strong>Meta</strong>: <em>Beep</em>' in html
    assert 'Unevaluated placeholder: {currency}' in html
    assert 'EUR' not in html
    assert re.search(
        r'Event website: <a href="https://example.org/dummy" rel="noopener" style="[^"]+" target="_blank">'
        r'&lt;strong&gt;event &amp; co. kg&lt;/strong&gt; {currency}</a>',
        html
    )


@pytest.mark.django_db
def test_placeholder_html_rendering_from_string(env):
    template = LazyI18nString({
        "en": "Event name: {event}\n\nPayment info:\n{payment_info}\n\n**Meta**: {meta_Test}\n\n"
              "Event website: [{event}](https://example.org/{event_slug})\n\n"
              "Other website: [{event}]({meta_Website})\n\n"
              "URL: {url}\n\n"
              "URL with text: <a href=\"{url}\">Test</a>\n\n"
              "URL with params: https://example.com/form?action=foo&eventid={event_slug}\n\n"
              "URL with params and text: [Link & Text](https://example.com/form?action=foo&eventid={event_slug})\n\n"
    })
    djmail.outbox = []
    event, user, organizer = env
    event.name = "<strong>event & co. kg</strong> {currency}"
    event.save()
    ctx = get_email_context(
        event=event,
        payment_info="**IBAN**: 123  \n**BIC**: 456",
    )
    ctx["url"] = "https://google.com"
    mail('dummy@dummy.dummy', '{event} Test subject', template, ctx, event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert 'Event name: <strong>event & co. kg</strong> {currency}' in djmail.outbox[0].body
    assert 'Event website: [<strong>event & co. kg</strong> {currency}](https://example.org/dummy)' in djmail.outbox[0].body
    assert 'Other website: [<strong>event & co. kg</strong> {currency}](https://example.com)' in djmail.outbox[0].body
    assert '**IBAN**: 123  \n**BIC**: 456' in djmail.outbox[0].body
    assert '**Meta**: *Beep*' in djmail.outbox[0].body
    assert 'URL: https://google.com' in djmail.outbox[0].body
    assert 'URL with text: <a href="https://google.com">Test</a>' in djmail.outbox[0].body
    assert 'URL with params: https://example.com/form?action=foo&eventid=dummy' in djmail.outbox[0].body
    assert 'URL with params and text: [Link & Text](https://example.com/form?action=foo&eventid=dummy)' in djmail.outbox[0].body
    assert '&lt;' not in djmail.outbox[0].body
    assert '&amp;' not in djmail.outbox[0].body
    html = _extract_html(djmail.outbox[0])
    assert '<strong>event' not in html
    assert 'Event name: &lt;strong&gt;event &amp; co. kg&lt;/strong&gt;' in html
    assert '<strong>IBAN</strong>: 123<br/>\n<strong>BIC</strong>: 456' in html
    assert '<strong>Meta</strong>: <em>Beep</em>' in html
    assert re.search(
        r'Event website: <a href="https://example.org/dummy" rel="noopener" style="[^"]+" target="_blank">'
        r'&lt;strong&gt;event &amp; co. kg&lt;/strong&gt; {currency}</a>',
        html
    )
    assert re.search(
        r'Other website: <a href="https://example.com" rel="noopener" style="[^"]+" target="_blank">'
        r'&lt;strong&gt;event &amp; co. kg&lt;/strong&gt; {currency}</a>',
        html
    )
    assert re.search(
        r'URL: <a href="https://google.com" rel="noopener" style="[^"]+" target="_blank">https://google.com</a>',
        html
    )
    assert re.search(
        r'URL with text: <a href="https://google.com" rel="noopener" style="[^"]+" target="_blank">Test</a>',
        html
    )
    assert re.search(
        r'URL with params: <a href="https://example.com/form\?action=foo&amp;eventid=dummy" rel="noopener" '
        r'style="[^"]+" target="_blank">https://example.com/form\?action=foo&amp;eventid=dummy</a>',
        html
    )
    assert re.search(
        r'URL with params and text: <a href="https://example.com/form\?action=foo&amp;eventid=dummy" rel="noopener" '
        r'style="[^"]+" target="_blank">Link &amp; Text</a>',
        html
    )


@pytest.mark.django_db
def test_nested_placeholder_inclusion_full_process(env, order):
    # Test that it is not possible to sneak in a placeholder like {url_cancel} inside a user-controlled
    # placeholder value like {invoice_company}
    event, user, organizer = env
    position = order.positions.get()
    order.invoice_address.company = "{url_cancel} Corp"
    order.invoice_address.save()
    event.settings.mail_text_resend_link = LazyI18nString({"en": "Ticket for {invoice_company}"})
    event.settings.mail_subject_resend_link_attendee = LazyI18nString({"en": "Ticket for {invoice_company}"})

    djmail.outbox = []
    position.resend_link()
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [position.attendee_email]
    assert "Ticket for {url_cancel} Corp" == djmail.outbox[0].subject
    assert "/cancel" not in djmail.outbox[0].body
    assert "/order" not in djmail.outbox[0].body
    html, plain = _extract_html(djmail.outbox[0]), djmail.outbox[0].body
    for part in (html, plain):
        assert "Ticket for {url_cancel} Corp" in part
        assert "/order/" not in part
        assert "/cancel" not in part


@pytest.mark.django_db
def test_nested_placeholder_inclusion_mail_service(env):
    # test that it is not possible to have placeholders within the values of placeholders when
    # the mail() function is called directly
    template = LazyI18nString("Event name: {event}")
    djmail.outbox = []
    event, user, organizer = env
    event.name = "event & {currency} co. kg"
    event.slug = "event-co-ag-slug"
    event.save()

    mail(
        "dummy@dummy.dummy",
        "{event} Test subject",
        template,
        get_email_context(
            event=event,
            payment_info="**IBAN**: 123  \n**BIC**: 456 {event}",
        ),
        event,
    )

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    html, plain = _extract_html(djmail.outbox[0]), djmail.outbox[0].body
    for part in (html, plain, djmail.outbox[0].subject):
        assert "event & {currency} co. kg" in part or "event &amp; {currency} co. kg" in part
        assert "EUR" not in part


@pytest.mark.django_db
@pytest.mark.parametrize("tpl", [
    "Event: {event.__class__}",
    "Event: {{event.__class__}}",
    "Event: {{{event.__class__}}}",
])
def test_variable_inclusion_from_string_full_process(env, tpl, order):
    # Test that it is not possible to use placeholders that leak system information in templates
    # when run through system processes
    event, user, organizer = env
    event.name = "event & co. kg"
    event.save()
    position = order.positions.get()
    event.settings.mail_text_resend_link = LazyI18nString({"en": tpl})
    event.settings.mail_subject_resend_link_attendee = LazyI18nString({"en": tpl})

    position.resend_link()
    assert len(djmail.outbox) == 1
    html, plain = _extract_html(djmail.outbox[0]), djmail.outbox[0].body
    for part in (html, plain, djmail.outbox[0].subject):
        assert "{event.__class__}" in part
        assert "LazyI18nString" not in part


@pytest.mark.django_db
@pytest.mark.parametrize("tpl", [
    "Event: {event.__class__}",
    "Event: {{event.__class__}}",
    "Event: {{{event.__class__}}}",
])
def test_variable_inclusion_from_string_mail_service(env, tpl):
    # Test that it is not possible to use placeholders that leak system information in templates
    # when run through mail() directly
    event, user, organizer = env
    event.name = "event & co. kg"
    event.save()

    djmail.outbox = []
    mail(
        "dummy@dummy.dummy",
        tpl,
        LazyI18nString(tpl),
        get_email_context(
            event=event,
            payment_info="**IBAN**: 123  \n**BIC**: 456\n" + tpl,
        ),
        event,
    )
    assert len(djmail.outbox) == 1
    html, plain = _extract_html(djmail.outbox[0]), djmail.outbox[0].body
    for part in (html, plain, djmail.outbox[0].subject):
        assert "{event.__class__}" in part
        assert "LazyI18nString" not in part


@pytest.mark.django_db
def test_escaped_braces_mail_services(env):
    # Test that braces can be escaped by doubling
    template = LazyI18nString("Event name: -{{currency}}-")
    djmail.outbox = []
    event, user, organizer = env
    event.name = "event & co. kg"
    event.save()

    mail(
        "dummy@dummy.dummy",
        "-{{currency}}- Test subject",
        template,
        get_email_context(
            event=event,
            payment_info="**IBAN**: 123  \n**BIC**: 456 {event}",
        ),
        event,
    )

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    html, plain = _extract_html(djmail.outbox[0]), djmail.outbox[0].body
    for part in (html, plain, djmail.outbox[0].subject):
        assert "EUR" not in part
        assert "-{currency}-" in part
