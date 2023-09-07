#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
# This file contains Apache-licensed contributions copyrighted by: Maico Timmerman
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import inspect
import json
from datetime import timedelta
from tempfile import NamedTemporaryFile
from typing import List
from zipfile import ZipFile

from dateutil.parser import parse
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretix.base.i18n import language
from pretix.base.models import CachedFile, Event, User, cachedfile_name
from pretix.base.services.mail import SendMailException, mail
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.shredder import ShredError
from pretix.celery_app import app


@app.task(base=ProfiledEventTask)
def export(event: Event, shredders: List[str], session_key=None, cfid=None) -> None:
    known_shredders = event.get_data_shredders()

    with NamedTemporaryFile() as rawfile:
        with ZipFile(rawfile, 'w') as zipfile:
            ccode = get_random_string(6)
            zipfile.writestr(
                'CONFIRM_CODE.txt',
                ccode,
            )
            zipfile.writestr(
                'index.json',
                json.dumps({
                    'instance': settings.SITE_URL,
                    'organizer': event.organizer.slug,
                    'event': event.slug,
                    'time': now().isoformat(),
                    'shredders': shredders,
                    'confirm_code': ccode
                }, indent=4)
            )
            for s in shredders:
                shredder = known_shredders.get(s)
                if not shredder:
                    continue

                it = shredder.generate_files()
                if not it:
                    continue
                for fname, ftype, content in it:
                    zipfile.writestr(fname, content)

        rawfile.seek(0)

        if cfid:
            cf = CachedFile.objects.get(pk=cfid)
        else:
            cf = CachedFile()
            cf.date = now()
            cf.session_key = session_key
            cf.web_download = True
            cf.expires = now() + timedelta(hours=1)
        cf.filename = event.slug + '.zip'
        cf.type = 'application/zip'
        cf.save()
        cf.file.save(cachedfile_name(cf, cf.filename), rawfile)

    return cf.pk


@app.task(base=ProfiledEventTask, throws=(ShredError,), bind=True)
def shred(self, event: Event, fileid: str, confirm_code: str, user: int=None, locale: str='en') -> None:
    steps = []

    if user:
        user = User.objects.get(pk=user)

    def set_progress(val):
        if not self.request.called_directly:
            self.update_state(
                state='PROGRESS',
                meta={'value': val, 'steps': steps}
            )

    known_shredders = event.get_data_shredders()
    try:
        cf = CachedFile.objects.get(pk=fileid)
    except CachedFile.DoesNotExist:
        raise ShredError(_("The download file could no longer be found on the server, please try to start again."))
    with ZipFile(cf.file.file, 'r') as zipfile:
        indexdata = json.loads(zipfile.read('index.json').decode())
    if indexdata['organizer'] != event.organizer.slug or indexdata['event'] != event.slug:
        raise ShredError(_("This file is from a different event."))
    shredders = []
    for s in indexdata['shredders']:
        shredder = known_shredders.get(s)
        if not shredder:
            continue
        shredders.append(shredder)
    if confirm_code is not True and any(shredder.require_download_confirmation for shredder in shredders):
        if indexdata['confirm_code'] != confirm_code:
            raise ShredError(_("The confirm code you entered was incorrect."))
    if event.logentry_set.filter(datetime__gte=parse(indexdata['time'])):
        raise ShredError(_("Something happened in your event after the export, please try again."))

    event.log_action(
        'pretix.event.shredder.started', user=user, data={
            'indexdata': indexdata
        }
    )

    for i, shredder in enumerate(shredders):
        with language(locale):
            steps.append({'label': str(shredder.verbose_name), 'done': False})
        set_progress(i * 100 / len(shredders))
        if 'progress_callback' in inspect.signature(shredder.shred_data).parameters:
            shredder.shred_data(
                progress_callback=lambda y: set_progress(
                    i * 100 / len(shredders) + min(max(y, 0), 100) / 100 * 100 / len(shredders)
                )
            )
        else:
            shredder.shred_data()
        steps[-1]['done'] = True

    cf.file.delete(save=False)
    cf.delete()

    event.log_action(
        'pretix.event.shredder.completed', user=user, data={
            'indexdata': indexdata
        }
    )

    if user:
        with language(user.locale):
            try:
                mail(
                    user.email,
                    _('Data shredding completed'),
                    'pretixbase/email/shred_completed.txt',
                    {
                        'user': user,
                        'organizer': event.organizer.name,
                        'event': str(event.name),
                        'start_time': date_format(parse(indexdata['time']).astimezone(event.timezone), 'SHORT_DATETIME_FORMAT'),
                        'shredders': ', '.join([str(s.verbose_name) for s in shredders])
                    },
                    event=None,
                    user=user,
                    locale=user.locale,
                )
            except SendMailException:
                pass  # Already logged
