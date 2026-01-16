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

import os
import re
from email.mime.text import MIMEText

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import scope
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.models import Event, Organizer, User
from pretix.base.services.mail import mail


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
    event.name = "<strong>event & co. kg</strong>"
    event.save()
    mail('dummy@dummy.dummy', '{event} Test subject', 'mailtest.txt', get_email_context(
        event=event,
        payment_info="**IBAN**: 123  \n**BIC**: 456",
    ), event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert 'Event name: <strong>event & co. kg</strong>' in djmail.outbox[0].body
    assert '**IBAN**: 123  \n**BIC**: 456' in djmail.outbox[0].body
    assert '**Meta**: *Beep*' in djmail.outbox[0].body
    assert 'Event website: [<strong>event & co. kg</strong>](https://example.org/dummy)' in djmail.outbox[0].body
    assert 'Other website: [<strong>event & co. kg</strong>](https://example.com)' in djmail.outbox[0].body
    assert '&lt;' not in djmail.outbox[0].body
    assert '&amp;' not in djmail.outbox[0].body
    html = _extract_html(djmail.outbox[0])

    assert '<strong>event' not in html
    assert 'Event name: &lt;strong&gt;event &amp; co. kg&lt;/strong&gt;' in html
    assert '<strong>IBAN</strong>: 123<br/>\n<strong>BIC</strong>: 456' in html
    assert '<strong>Meta</strong>: <em>Beep</em>' in html
    assert re.search(
        r'Event website: <a href="https://example.org/dummy" rel="noopener" style="[^"]+" target="_blank">&lt;strong&gt;event &amp; co. kg&lt;/strong&gt;</a>',
        html
    )
    assert re.search(
        r'Other website: <a href="https://example.com" rel="noopener" style="[^"]+" target="_blank">&lt;strong&gt;event &amp; co. kg&lt;/strong&gt;</a>',
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
    event.name = "<strong>event & co. kg</strong>"
    event.save()
    ctx = get_email_context(
        event=event,
        payment_info="**IBAN**: 123  \n**BIC**: 456",
    )
    ctx["url"] = "https://google.com"
    mail('dummy@dummy.dummy', '{event} Test subject', template, ctx, event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert 'Event name: <strong>event & co. kg</strong>' in djmail.outbox[0].body
    assert 'Event website: [<strong>event & co. kg</strong>](https://example.org/dummy)' in djmail.outbox[0].body
    assert 'Other website: [<strong>event & co. kg</strong>](https://example.com)' in djmail.outbox[0].body
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
        r'Event website: <a href="https://example.org/dummy" rel="noopener" style="[^"]+" target="_blank">&lt;strong&gt;event &amp; co. kg&lt;/strong&gt;</a>',
        html
    )
    assert re.search(
        r'Other website: <a href="https://example.com" rel="noopener" style="[^"]+" target="_blank">&lt;strong&gt;event &amp; co. kg&lt;/strong&gt;</a>',
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
